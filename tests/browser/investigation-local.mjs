import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile} from 'node:fs/promises';
import {join} from 'node:path';
import {chromium} from 'playwright';

const publicDir = new URL('../../public/', import.meta.url);
const snapshot = {manifest:{schema_version:1,last_scan_at:new Date().toISOString(),
  data_status:'fresh'},events:[
  {kind:'satellite_candidate',event_id:'older',latitude:-6.025,longitude:145.025,
    observed_at:new Date(Date.now()-4*3_600_000).toISOString(),sources:['VIIRS_NOAA20_NRT']},
  {kind:'satellite_candidate',event_id:'latest',latitude:-6.025,longitude:145.025,
    observed_at:new Date(Date.now()-3_600_000).toISOString(),sources:['VIIRS_NOAA21_NRT']}],
  incidents:[],matches:[],sources:[
    {key:'VIIRS_NOAA20_NRT',status:'complete'},
    {key:'VIIRS_NOAA21_NRT',status:'complete'}]};
let activeSnapshot = snapshot;
const server = createServer(async (request,response) => {
  if (request.url === '/api/snapshot') {
    response.setHeader('Content-Type','application/json');
    response.end(JSON.stringify(activeSnapshot));
    return;
  }
  const name = request.url === '/' ? 'index.html' : request.url.slice(1);
  if (!['index.html','style.css','main.mjs','map-state.mjs','area-analysis.mjs',
    'incident-timeline.mjs','weather-context.mjs'].includes(name)) {
    response.writeHead(404).end(); return;
  }
  response.setHeader('Content-Type',name.endsWith('.css') ? 'text/css'
    : name.endsWith('.mjs') ? 'text/javascript' : 'text/html');
  response.end(await readFile(join(publicDir.pathname,name)));
});
await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
const browser = await chromium.launch({headless:true,
  ...(process.env.CHROMIUM_PATH ? {executablePath:process.env.CHROMIUM_PATH} : {})});
try {
  for (const viewport of [{width:1366,height:768},{width:390,height:844}]) {
    const page = await browser.newPage({viewport});
    const errors = [];
    page.on('pageerror',error => errors.push(error.message));
    await page.goto(`http://127.0.0.1:${server.address().port}/#lang=tr&lat=-6&lon=145&zoom=7`);
    const lead = page.locator('#lead-list button').first();
    await lead.waitFor({timeout:30000});
    assert.equal(await lead.getAttribute('data-event-id'),'latest');
    assert.match(await lead.textContent(),/2 ayrı saatte gözlendi/);
    await lead.click();
    assert.equal(await page.locator('#detail').isVisible(),true);
    assert.match(await page.locator('#detail-content').textContent(),/latest/);
    await page.waitForFunction(() => location.hash.includes('lat=-6.025') &&
      location.hash.includes('lon=145.025'));
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),false);
    assert.deepEqual(errors,[]);
    if (process.env.SCREENSHOT_DIR)
      await page.screenshot({path:`${process.env.SCREENSHOT_DIR}/investigation-${viewport.width}.png`});
    await page.close();
  }
  activeSnapshot = {...snapshot,events:[],manifest:{...snapshot.manifest,
    last_scan_at:new Date(Date.now()-3*3_600_000).toISOString()}};
  const stale = await browser.newPage();
  await stale.goto(`http://127.0.0.1:${server.address().port}/#lang=tr&lat=-6&lon=145&zoom=7`);
  await stale.locator('#lead-quality').getByText('Veri görüntüsü eski').waitFor();
  assert.equal(await stale.locator('#lead-list button').count(),0);
  assert.match(await stale.locator('#lead-empty').textContent(),/yangın olmadığı anlamına gelmez/);
  await stale.close();
  activeSnapshot = {...snapshot,manifest:{...snapshot.manifest,data_status:'partial'},
    sources:[{key:'VIIRS_NOAA20_NRT',status:'failed'},
      {key:'VIIRS_NOAA21_NRT',status:'complete'}]};
  const partial = await browser.newPage();
  await partial.goto(`http://127.0.0.1:${server.address().port}/#lang=tr&lat=-6&lon=145&zoom=7`);
  await partial.locator('#lead-quality').getByText('Bazı uydu kaynakları başarısız').waitFor();
  await partial.close();
  activeSnapshot = {...activeSnapshot,manifest:{...activeSnapshot.manifest,
    last_scan_at:new Date(Date.now()-3*3_600_000).toISOString()}};
  const combined = await browser.newPage();
  await combined.goto(`http://127.0.0.1:${server.address().port}/#lang=tr&kind=incident&lat=-6&lon=145&zoom=7`);
  await combined.locator('#lead-list button').first().waitFor();
  const warnings = await combined.locator('#lead-quality').textContent();
  assert.match(warnings,/Veri görüntüsü eski/);
  assert.match(warnings,/Bazı uydu kaynakları başarısız/);
  await combined.close();

  activeSnapshot = {...snapshot,manifest:{...snapshot.manifest,
    last_scan_at:new Date(Date.now()-89*60_000).toISOString()}};
  const aging = await browser.newPage();
  await aging.clock.install();
  await aging.goto(`http://127.0.0.1:${server.address().port}/#lang=tr&lat=-6&lon=145&zoom=7`);
  await aging.locator('#lead-list button').first().waitFor();
  assert.equal(await aging.locator('#lead-quality').textContent(),'');
  await aging.clock.fastForward(2*60_000);
  await aging.locator('#lead-quality').getByText('Veri görüntüsü eski').waitFor();
  await aging.close();

  activeSnapshot = {...snapshot,events:[{...snapshot.events[1],
    observed_at:new Date(Date.now()-11*3_600_000-59*60_000).toISOString()}]};
  const expiring = await browser.newPage();
  await expiring.clock.install();
  await expiring.goto(`http://127.0.0.1:${server.address().port}/#lang=tr&lat=-6&lon=145&zoom=7`);
  await expiring.locator('#lead-list button').first().waitFor();
  await expiring.clock.fastForward(2*60_000);
  await expiring.locator('#lead-empty:visible').waitFor();
  await expiring.close();

  const firstSeen = new Date(Date.now()-2*3_600_000).toISOString();
  const changed = new Date(Date.now()-3_600_000).toISOString();
  activeSnapshot = {...snapshot,events:[],incidents:[{kind:'agency_incident',provider:'cwfis',
    official_id:'CA-1',name:'Test fire',incident_kind:'active_wildland_fire',
    latitude:-6,longitude:145,modified_at:changed,agency_status:'BH'}],
    details:{incident_history:{'cwfis:CA-1':[
      {change:'first_seen',seen_at:firstSeen,agency_status:'OC',source_modified_at:firstSeen},
      {change:'record_changed',seen_at:changed,agency_status:'BH',source_modified_at:changed}]}}};
  const incidentPage = await browser.newPage({viewport:{width:1366,height:768}});
  await incidentPage.goto(`http://127.0.0.1:${server.address().port}/#lang=tr&kind=incident&lat=-6&lon=145&zoom=7`);
  await incidentPage.locator('#incident-count').getByText('1').waitFor();
  const mapBox = await incidentPage.locator('#map canvas.maplibregl-canvas').boundingBox();
  for (let attempt=0;attempt<30 && !await incidentPage.locator('#detail').isVisible();attempt++) {
    await incidentPage.mouse.click(mapBox.x+mapBox.width/2,mapBox.y+mapBox.height/2);
    await incidentPage.waitForTimeout(500);
  }
  await incidentPage.locator('#detail:visible').waitFor();
  const detail = await incidentPage.locator('#detail-content').textContent();
  assert.match(detail,/Kurum kaydı değişim geçmişi/);
  assert.match(detail,/Kontrol dışı/);
  assert.match(detail,/Sınırları içinde tutuluyor/);
  assert.match(detail,/Yangının yayılma geçmişi değildir/);
  await incidentPage.close();

  activeSnapshot = {...snapshot,events:[],incidents:[{kind:'agency_incident',
    provider:'nifc_wfigs',official_id:'US-1',name:'US test event',incident_kind:'WF',
    latitude:39.7456,longitude:-97.0892,modified_at:new Date().toISOString()}],
    details:{incident_history:{}}};
  const weatherPage = await browser.newPage({viewport:{width:1366,height:768}});
  const weatherCalls = [];
  await weatherPage.route('https://api.weather.gov/**',route => {
    weatherCalls.push(route.request().url());
    const from = new Date(Date.now()-3_600_000).toISOString();
    const later = new Date(Date.parse(from)+6*3_600_000).toISOString();
    const response = route.request().url().includes('/points/')
      ? {properties:{forecastGridData:'https://api.weather.gov/gridpoints/TOP/32,81'}}
      : {properties:{updateTime:from,
          windSpeed:{uom:'wmoUnit:km_h-1',values:[{validTime:`${from}/PT6H`,value:20},
            {validTime:`${later}/P2D`,value:35}]},
          windDirection:{uom:'wmoUnit:degree_(angle)',values:[{validTime:`${from}/PT6H`,value:350},
            {validTime:`${later}/P2D`,value:10}]},
          windGust:{uom:'wmoUnit:km_h-1',values:[{validTime:`${from}/PT6H`,value:35},
            {validTime:`${later}/P2D`,value:50}]},
          temperature:{uom:'wmoUnit:degC',values:[{validTime:`${from}/PT6H`,value:28},
            {validTime:`${later}/P2D`,value:31}]},
          relativeHumidity:{uom:'wmoUnit:percent',values:[{validTime:`${from}/PT6H`,value:30},
            {validTime:`${later}/P2D`,value:20}]},
          quantitativePrecipitation:{uom:'wmoUnit:mm',values:[{validTime:`${from}/P2D`,value:0}]}}};
    return route.fulfill({status:200,contentType:'application/geo+json',body:JSON.stringify(response)});
  });
  await weatherPage.goto(`http://127.0.0.1:${server.address().port}/#lang=tr&kind=incident&lat=39.7456&lon=-97.0892&zoom=7`);
  await weatherPage.locator('#incident-count').getByText('1').waitFor();
  const weatherMapBox = await weatherPage.locator('#map canvas.maplibregl-canvas').boundingBox();
  for (let attempt=0;attempt<30 && !await weatherPage.locator('#detail').isVisible();attempt++) {
    await weatherPage.mouse.click(weatherMapBox.x+weatherMapBox.width/2,
      weatherMapBox.y+weatherMapBox.height/2);
    await weatherPage.waitForTimeout(500);
  }
  await weatherPage.locator('.weather-context').getByText('Rüzgâr: 20 km/h').first().waitFor();
  assert.equal(weatherCalls.length,2);
  const weatherDetail = await weatherPage.locator('.weather-context').textContent();
  assert.match(weatherDetail,/Hamle: 35 km\/h/);
  assert.match(weatherDetail,/Tahmini yağış: 0 mm/);
  assert.match(weatherDetail,/yayılım tahmini değildir/);
  const changeDetail = await weatherPage.locator('.weather-change-analysis').textContent();
  assert.match(changeDetail,/Tahmini hava değişimi/);
  assert.match(changeDetail,/Rüzgâr: \+15 km\/h/);
  assert.match(changeDetail,/Nem: -10 %/);
  assert.match(changeDetail,/yayılma olasılığı değildir/);
  const headings = await weatherPage.locator('#detail-content h3').allTextContents();
  assert.ok(headings.indexOf('Kayıt konumundaki hava') < headings.indexOf('Kurum kaydı değişim geçmişi'));
  await weatherPage.locator('.weather-context details summary').first().click();
  assert.match(await weatherPage.locator('.weather-context details').first().textContent(),
    /Kaynak geçerlilik aralıkları.*Rüzgâr/s);
  if (process.env.SCREENSHOT_DIR)
    await weatherPage.screenshot({path:`${process.env.SCREENSHOT_DIR}/weather-context.png`});
  await weatherPage.setViewportSize({width:390,height:844});
  assert.equal(await weatherPage.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),false);
  assert.equal(await weatherPage.locator('.weather-context').isVisible(),true);
  if (process.env.SCREENSHOT_DIR)
    await weatherPage.screenshot({path:`${process.env.SCREENSHOT_DIR}/weather-context-mobile.png`});
  await weatherPage.close();
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
