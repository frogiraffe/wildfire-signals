import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const url = 'https://wildfire-signals.pages.dev/#3/15/-60';
const browser = await chromium.launch({headless: true});

try {
  for (const viewport of [{width: 1366, height: 768}, {width: 390, height: 844}]) {
    const page = await browser.newPage({viewport});
    const failures = [];
    page.on('pageerror', error => failures.push(error.message));
    try {
      const response = await page.goto(url, {waitUntil: 'domcontentloaded', timeout: 30000});
      assert.equal(response?.status(), 200, 'map page should load');
      await page.waitForFunction(() => {
        const count = Number((document.querySelector('#candidate-count')?.textContent || '').replace(/\D/g, ''));
        const canvas = document.querySelector('#map canvas.maplibregl-canvas');
        return count > 0 && canvas?.width > 0;
      }, null, {timeout: 60000});

      const result = await page.evaluate(() => ({
        candidateCount: Number(document.querySelector('#candidate-count').textContent.replace(/\D/g, '')),
        incidentCount: Number(document.querySelector('#incident-count').textContent.replace(/\D/g, '')),
        sourceCount: document.querySelectorAll('#source-list li').length,
        lastScan: document.querySelector('#last-scan').textContent,
        horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
      }));
      assert.ok(result.candidateCount > 0, 'live satellite candidates should be visible');
      assert.ok(result.incidentCount > 0, 'live agency incidents should be visible');
      assert.equal(result.sourceCount, 4, 'four source states should be present');
      assert.notEqual(result.lastScan, '–', 'scan time should be populated');
      assert.equal(result.horizontalOverflow, false, 'page should fit the viewport');
      await page.locator('#hours').selectOption('72');
      await page.waitForFunction(previous => {
        const count = Number((document.querySelector('#candidate-count')?.textContent || '').replace(/\D/g, ''));
        return count > previous;
      }, result.candidateCount, {timeout: 30000});
      const threeDayCount = Number((await page.locator('#candidate-count').textContent()).replace(/\D/g, ''));
      assert.ok(threeDayCount > result.candidateCount,
        '72-hour view should contain observations absent from the 24-hour view');
      assert.deepEqual(failures, [], 'page should have no uncaught JavaScript errors');
      console.log(JSON.stringify({viewport: `${viewport.width}x${viewport.height}`,
        ...result, threeDayCount}));
    } finally {
      await page.close();
    }
  }
} finally {
  await browser.close();
}
