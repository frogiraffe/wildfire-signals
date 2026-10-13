import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {chromium} from 'playwright';

const files = new Map([
  ['/analytics.html', ['analytics.html','text/html']],
  ['/analytics.css', ['analytics.css','text/css']],
  ['/style.css', ['style.css','text/css']],
  ['/analytics-page.mjs', ['analytics-page.mjs','text/javascript']],
  ['/analytics-data.mjs', ['analytics-data.mjs','text/javascript']],
  ['/data/thermal-capture-pilot-2026-10-13.json',
    ['data/thermal-capture-pilot-2026-10-13.json','application/json']]
]);
const root = new URL('../../public/', import.meta.url);
const server = createServer(async (request,response) => {
  const entry = files.get(request.url);
  if (!entry) {response.writeHead(404).end(); return;}
  response.setHeader('Content-Type',entry[1]);
  response.end(await readFile(new URL(entry[0],root)));
});
await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
const browser = await chromium.launch({headless:true,
  ...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {})});
try {
  for (const viewport of [{width:1280,height:800},{width:390,height:844}]) {
    const page = await browser.newPage({viewport});
    const errors = []; page.on('pageerror',error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
    await page.locator('#analytics-status').getByText('Archived pilot loaded.').waitFor();
    assert.equal(await page.locator('#analytics-region option').count(),12);
    assert.ok(await page.locator('#analytics-days tr').count() > 0);
    assert.equal(await page.locator('#analytics-comparison tr').count(),12);
    assert.match(await page.locator('.analytics-warning').textContent(),/not confirmed wildfires/);
    await page.locator('#analytics-region').selectOption('ZAMBIA');
    assert.match(await page.locator('#analytics-selection-note').textContent(),/ZAMBIA/);
    await page.locator('#analytics-from').fill('2026-10-13');
    await page.locator('#analytics-to').fill('2026-10-13');
    assert.ok(await page.locator('#analytics-days tr').count() <= 1);
    assert.deepEqual(errors,[]);
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.close();
  }
} finally {await browser.close(); await new Promise(resolve => server.close(resolve));}
