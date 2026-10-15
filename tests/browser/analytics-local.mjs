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
  ['/historical-evidence.mjs', ['historical-evidence.mjs','text/javascript']],
  ['/historical-timeline.mjs', ['historical-timeline.mjs','text/javascript']],
  ['/historical-grid.mjs', ['historical-grid.mjs','text/javascript']],
  ['/historical-audit.mjs', ['historical-audit.mjs','text/javascript']],
  ['/data/thermal-capture-pilot-2026-10-13.json',
    ['data/thermal-capture-pilot-2026-10-13.json','application/json']],
  ['/data/batman-weather-context-2026-10-11.json',
    ['data/batman-weather-context-2026-10-11.json','application/json']],
  ['/data/sacramento-weather-context-2026-10-11.json',
    ['data/sacramento-weather-context-2026-10-11.json','application/json']],
  ['/data/batman-cmr-context-2026-10-11.json',
    ['data/batman-cmr-context-2026-10-11.json','application/json']],
  ['/data/batman-cmr-paired-products-2026-10-11.json',
    ['data/batman-cmr-paired-products-2026-10-11.json','application/json']],
  ['/data/antalya-annual-context-2023-2025.json',
    ['data/antalya-annual-context-2023-2025.json','application/json']],
  ['/data/dalaman-annual-context-2023-2025.json',
    ['data/dalaman-annual-context-2023-2025.json','application/json']],
  ['/data/turkey-spatial-recurrence-2023-2025.json',
    ['data/turkey-spatial-recurrence-2023-2025.json','application/json']],
  ['/data/antalya-standard-granule-readiness-2025-01-06-07.json',
    ['data/antalya-standard-granule-readiness-2025-01-06-07.json','application/json']],
  ['/data/turkey-static-sensitivity-2023-2025.json',
    ['data/turkey-static-sensitivity-2023-2025.json','application/json']],
  ['/data/sacramento-frap-outcome-cohort-2023-2025.json',
    ['data/sacramento-frap-outcome-cohort-2023-2025.json','application/json']]
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
    await page.locator('#annual-status').getByText('Three-year archive loaded.').waitFor();
    await page.locator('#spatial-status').getByText('Spatial recurrence evidence loaded.').waitFor();
    await page.locator('#unified-study').selectOption('DALAMAN_25KM');
    await page.locator('#unified-sensor').selectOption('VIIRS_SNPP_STANDARD');
    await page.locator('#unified-apply').click();
    assert.equal(await page.locator('#annual-region').inputValue(),'DALAMAN_25KM');
    assert.equal(await page.locator('#spatial-region').inputValue(),'DALAMAN_25KM');
    assert.equal(await page.locator('#annual-provider').inputValue(),'VIIRS_SNPP_STANDARD');
    assert.equal(await page.locator('#spatial-grid-sensor').inputValue(),'VIIRS_SNPP_STANDARD');
    assert.match(await page.locator('#unified-status').textContent(),/Applied DALAMAN/);
    await page.locator('#unified-study').selectOption('ANTALYA_25KM');
    await page.locator('#unified-sensor').selectOption('all');
    await page.locator('#unified-apply').click();
    await page.locator('#standard-readiness-status').getByText('Standard product research evidence loaded.').waitFor();
    await page.locator('#sensitivity-status').getByText('Real source sensitivity loaded.').waitFor();
    await page.locator('#frap-status').getByText('Official perimeter evidence loaded.').waitFor();
    assert.match(await page.locator('#sensitivity-summary').textContent(),/887/);
    assert.equal(await page.locator('#sensitivity-rows tr').count(),6);
    assert.equal(await page.locator('#frap-cases tr').count(),9);
    assert.match(await page.locator('#frap-summary').textContent(),/Verified fire-negative units: 0/);
    await page.locator('#sensitivity-region').selectOption('DALAMAN_25KM');
    assert.match(await page.locator('#sensitivity-summary').textContent(),/79 original archived pixels/);
    assert.match(await page.locator('#sensitivity-summary').textContent(),/0 lie in 0 unresolved/);
    assert.equal(await page.locator('#standard-readiness-days tr').count(),2);
    assert.match(await page.locator('#standard-readiness-days tr:last-child').textContent(),/opportunity unknown/);
    assert.match(await page.locator('#standard-readiness-gates').textContent(),/No model was trained/);
    assert.equal(await page.locator('#spatial-region option').count(),2);
    assert.match(await page.locator('#spatial-summary').textContent(),/1,340 archived pixels/);
    assert.match(await page.locator('#spatial-bins tr:first-child').textContent(),/748/);
    assert.match(await page.locator('#spatial-bins tr:first-child').textContent(),/Potential static source/);
    assert.equal(await page.locator('#spatial-year-quality tr').count(),3);
    assert.match(await page.locator('#spatial-year-quality tr:first-child').textContent(),/480/);
    await page.locator('#spatial-region').selectOption('DALAMAN_25KM');
    assert.match(await page.locator('#spatial-summary').textContent(),/79 archived pixels/);
    assert.match(await page.locator('#spatial-summary').textContent(),/4 bins recur/);
    assert.match(await page.locator('#spatial-year-quality tr:last-child').textContent(),/3/);
    assert.equal(await page.locator('#annual-region option').count(),2);
    assert.equal(await page.locator('#annual-region').inputValue(),'ANTALYA_25KM');
    assert.equal(await page.locator('#annual-year-comparison tr').count(),6);
    assert.equal(await page.locator('#annual-months tr').count(),36);
    assert.match(await page.locator('#annual-provenance').textContent(),/257,907 rows/);
    assert.match(await page.locator('#annual-summary').textContent(),/1,340 archived candidate pixels/);
    await page.locator('#annual-from').fill('2025-01');
    assert.equal(await page.locator('#annual-months tr').count(),12);
    assert.match(await page.locator('#annual-summary').textContent(),/212 archived candidate pixels/);
    await page.locator('#annual-provider').selectOption('VIIRS_NOAA20_STANDARD');
    assert.match(await page.locator('#annual-summary').textContent(),/107 archived candidate pixels/);
    await page.locator('#annual-variable').selectOption('wind_speed_m_s');
    assert.match(await page.locator('#annual-weather-chart').getAttribute('aria-label'),/Wind speed/);
    await page.locator('#annual-to').fill('2024-12');
    assert.match(await page.locator('#annual-status').textContent(),/Invalid annual selection/);
    await page.locator('#annual-to').fill('2025-12');
    await page.locator('#annual-region').selectOption('DALAMAN_25KM');
    assert.match(await page.locator('#annual-provenance').textContent(),/79 selected pixels/);
    assert.match(await page.locator('#annual-summary').textContent(),/23 archived candidate pixels/);
    assert.match(await page.locator('#annual-download').getAttribute('href'),/dalaman-annual/);
    assert.match(await page.locator('#annual-year-comparison tr:last-child').textContent(),/53/);
    assert.equal(await page.locator('#weather-region option').count(),2);
    assert.equal(await page.locator('#weather-comparison tr').count(),2);
    await page.locator('#catalog-status').getByText('CMR catalog context loaded.').waitFor();
    await page.locator('#pair-status').getByText('Active-fire product catalog context loaded.').waitFor();
    assert.equal(await page.locator('#catalog-candidates tr').count(),7);
    assert.match(await page.locator('#catalog-summary').textContent(),/20 granules/);
    assert.match(await page.locator('#catalog-summary').textContent(),/not cell-level observation opportunity/);
    assert.match(await page.locator('#pair-summary').textContent(),/20 exact same-platform/);
    assert.match(await page.locator('#pair-summary').textContent(),/5\/7 archived provider-minute/);
    assert.match(await page.locator('#catalog-candidates tr:first-child').textContent(),/L2 product catalogued/);
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
  const missingPair = await browser.newPage();
  await missingPair.route('**/data/batman-cmr-paired-products-2026-10-11.json', route =>
    route.fulfill({status:503,body:'unavailable'}));
  await missingPair.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
  await missingPair.locator('#catalog-status').getByText('CMR catalog context loaded.').waitFor();
  await missingPair.locator('#pair-status').getByText(/context unavailable/).waitFor();
  assert.equal(await missingPair.locator('#catalog-candidates tr').count(),7);
  assert.match(await missingPair.locator('#catalog-candidates tr:first-child').textContent(),/Catalog unavailable/);
  await missingPair.close();
  const missingAnnual = await browser.newPage();
  await missingAnnual.route('**/data/antalya-annual-context-2023-2025.json', route =>
    route.fulfill({status:503,body:'unavailable'}));
  await missingAnnual.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
  await missingAnnual.locator('#annual-status').getByText(/one study unavailable/).waitFor();
  await missingAnnual.locator('#weather-status').getByText('Retrospective station pilot loaded.').waitFor();
  assert.equal(await missingAnnual.locator('#annual-region option').count(),1);
  assert.equal(await missingAnnual.locator('#annual-region').inputValue(),'DALAMAN_25KM');
  assert.equal(await missingAnnual.locator('#annual-months tr').count(),36);
  await missingAnnual.close();
  const missingSpatial = await browser.newPage();
  await missingSpatial.route('**/data/turkey-spatial-recurrence-2023-2025.json', route =>
    route.fulfill({status:503,body:'unavailable'}));
  await missingSpatial.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
  await missingSpatial.locator('#spatial-status').getByText(/Spatial recurrence unavailable/).waitFor();
  await missingSpatial.locator('#annual-status').getByText('Three-year archive loaded.').waitFor();
  assert.equal(await missingSpatial.locator('#spatial-bins tr').count(),0);
  await missingSpatial.close();
  const missingStandard = await browser.newPage();
  await missingStandard.route('**/data/antalya-standard-granule-readiness-2025-01-06-07.json',
    route => route.fulfill({status:503,body:'unavailable'}));
  await missingStandard.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
  await missingStandard.locator('#standard-readiness-status').getByText(/evidence unavailable/).waitFor();
  assert.equal(await missingStandard.locator('#standard-readiness-days tr').count(),0);
  await missingStandard.close();
  const missingSensitivity = await browser.newPage();
  await missingSensitivity.route('**/data/turkey-static-sensitivity-2023-2025.json',
    route => route.fulfill({status:503,body:'unavailable'}));
  await missingSensitivity.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
  await missingSensitivity.locator('#sensitivity-status').getByText(/Source sensitivity unavailable/).waitFor();
  assert.equal(await missingSensitivity.locator('#sensitivity-rows tr').count(),0);
  await missingSensitivity.close();
  const missingFrap = await browser.newPage();
  await missingFrap.route('**/data/sacramento-frap-outcome-cohort-2023-2025.json',
    route => route.fulfill({status:503,body:'unavailable'}));
  await missingFrap.goto(`http://127.0.0.1:${server.address().port}/analytics.html`);
  await missingFrap.locator('#frap-status').getByText(/Official perimeter evidence unavailable/).waitFor();
  assert.equal(await missingFrap.locator('#frap-cases tr').count(),0);
  await missingFrap.close();
} finally {await browser.close(); await new Promise(resolve => server.close(resolve));}
