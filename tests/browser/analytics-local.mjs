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
    ['data/thermal-capture-pilot-2026-10-13.json','application/json']],
  ['/data/batman-weather-context-2026-10-11.json',
    ['data/batman-weather-context-2026-10-11.json','application/json']],
  ['/data/sacramento-weather-context-2026-10-11.json',
    ['data/sacramento-weather-context-2026-10-11.json','application/json']],
  ['/data/batman-cmr-context-2026-10-11.json',
    ['data/batman-cmr-context-2026-10-11.json','application/json']]
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
    await page.locator('#weather-status').getByText('Retrospective station pilot loaded.').waitFor();
    assert.equal(await page.locator('#weather-region option').count(),2);
    assert.equal(await page.locator('#weather-comparison tr').count(),2);
    await page.locator('#catalog-status').getByText('CMR catalog context loaded.').waitFor();
    assert.equal(await page.locator('#catalog-candidates tr').count(),7);
    assert.match(await page.locator('#catalog-summary').textContent(),/20 granules/);
    assert.match(await page.locator('#catalog-summary').textContent(),/not cell-level observation opportunity/);
    assert.equal(await page.locator('#weather-candidates tr').count(),6);
    assert.match(await page.locator('#weather-provenance').textContent(),/first availability is unknown/);
    assert.match(await page.locator('#weather-provenance').textContent(),/CC0-1.0/);
    await page.locator('#weather-variable').selectOption('wind_speed_m_s');
    assert.match(await page.locator('#weather-chart').getAttribute('aria-label'),/Wind speed/);
    await page.locator('#weather-region').selectOption('SACRAMENTO_25KM');
    assert.equal(await page.locator('#weather-candidates tr').count(),6);
    assert.match(await page.locator('#weather-provenance').textContent(),/USW00093225/);
    assert.match(await page.locator('#weather-summary').textContent(),/5\/6 candidate hours matched/);
    assert.match(await page.locator('#weather-download').getAttribute('href'),/sacramento-weather/);
    assert.equal(await page.locator('#analytics-region option').count(),12);
    assert.ok(await page.locator('#analytics-days tr').count() > 0);
    assert.equal(await page.locator('#analytics-comparison tr').count(),12);
    assert.match(await page.locator('.analytics-warning').textContent(),/not confirmed wildfires/);
    await page.locator('#analytics-region').selectOption('ZAMBIA');
    assert.match(await page.locator('#analytics-selection-note').textContent(),/ZAMBIA/);
    await page.locator('#analytics-from').fill('2026-10-13');
    await page.locator('#analytics-to').fill('2026-10-13');
    assert.ok(await page.locator('#analytics-days tr').count() <= 1);
    await page.locator('#analytics-from').fill('2026-10-13');
    await page.locator('#analytics-to').fill('2026-10-09');
    assert.equal(await page.locator('#analytics-days tr').count(),0);
    assert.match(await page.locator('#analytics-status').textContent(),/Invalid region or UTC date range/);
    assert.deepEqual(errors,[]);
    const overflow = await page.evaluate(() => ({width:innerWidth,
      scroll:document.documentElement.scrollWidth,
      containers:[...document.querySelectorAll('.analytics-shell,.analytics-main,.analytics-card,.analytics-table-wrap')].map(item => ({className:item.className,left:item.getBoundingClientRect().left,right:item.getBoundingClientRect().right,scroll:item.scrollWidth,client:item.clientWidth})),
      elements:[...document.querySelectorAll('*')].filter(item =>
        item.getBoundingClientRect().right > innerWidth + 1).slice(0,8).map(item =>
          ({tag:item.tagName,id:item.id,className:item.className,
            right:item.getBoundingClientRect().right}))}));
    assert.ok(overflow.scroll <= overflow.width + 1, JSON.stringify(overflow));
    await page.close();
  }
  const unavailable = await browser.newPage({viewport:{width:390,height:844}});
  await unavailable.route('**/data/batman-weather-context-2026-10-11.json', route =>
    route.fulfill({status:503,body:'unavailable'}));
  await unavailable.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
  await unavailable.locator('#analytics-status').getByText('Archived pilot loaded.').waitFor();
  await unavailable.locator('#weather-status').getByText(/Historical weather context unavailable/).waitFor();
  assert.equal(await unavailable.locator('#weather-region option').count(),1);
  assert.equal(await unavailable.locator('#weather-region').inputValue(),'SACRAMENTO_25KM');
  assert.equal(await unavailable.locator('#weather-candidates tr').count(),6);
  await unavailable.close();
  const noStations = await browser.newPage({viewport:{width:390,height:844}});
  await noStations.route('**/*-weather-context-2026-10-11.json', route =>
    route.fulfill({status:503,body:'unavailable'}));
  await noStations.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
  await noStations.locator('#weather-status').getByText(/neither source report loaded/).waitFor();
  assert.equal(await noStations.locator('#weather-region option').count(),0);
  assert.equal(await noStations.locator('#weather-chart .analytics-bar').count(),0);
  await noStations.close();
  const missingCatalog = await browser.newPage();
  await missingCatalog.route('**/data/batman-cmr-context-2026-10-11.json', route =>
    route.fulfill({status:503,body:'unavailable'}));
  await missingCatalog.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
  await missingCatalog.locator('#catalog-status').getByText(/CMR catalog context unavailable/).waitFor();
  assert.equal(await missingCatalog.locator('#catalog-candidates tr').count(),0);
  await missingCatalog.close();
} finally {await browser.close(); await new Promise(resolve => server.close(resolve));}
