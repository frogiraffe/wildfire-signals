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
  if (!['index.html','style.css','main.mjs','map-state.mjs','area-analysis.mjs'].includes(name)) {
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
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}
