import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const host = process.env.PAGES_HOST || 'wildfire-signals.pages.dev';
assert.match(host, /^(?:[a-f0-9]{8}\.)?wildfire-signals\.pages\.dev$/);
const url = `https://${host}/#lat=15&lon=-60&zoom=3`;
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
      await page.goto(`https://${host}/#lang=tr&hours=24&lat=-8.5&lon=140.5&zoom=7`,
        {waitUntil: 'domcontentloaded', timeout: 30000});
      await page.waitForFunction(() =>
        Number((document.querySelector('#area-candidates')?.textContent || '').replace(/\D/g, '')) > 0,
      null, {timeout: 60000});
      const area = await page.evaluate(() => ({
        title: document.querySelector('#area-title').textContent,
        candidateCount: Number(document.querySelector('#area-candidates').textContent.replace(/\D/g, '')),
        latest: document.querySelector('#area-latest').textContent,
        horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
      }));
      assert.equal(area.title, 'Görünen harita alanı');
      assert.ok(area.candidateCount > 0, 'Merauke viewport should show observed candidates');
      assert.notEqual(area.latest, '—', 'area should show the latest observation');
      assert.equal(area.horizontalOverflow, false, 'area analysis should fit the viewport');
      assert.deepEqual(failures, [], 'page should have no uncaught JavaScript errors');
      console.log(JSON.stringify({viewport: `${viewport.width}x${viewport.height}`,
        ...result, threeDayCount, meraukeArea:area}));
    } finally {
      await page.close();
    }
  }
} finally {
  await browser.close();
}
