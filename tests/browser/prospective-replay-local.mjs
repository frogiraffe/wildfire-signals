import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {chromium} from 'playwright';

const root=await mkdtemp(join(tmpdir(),'wildfire-agency-time-machine-'));
const cwd=new URL('../../',import.meta.url).pathname;
const make=spawnSync('python',['tests/browser/generate-prospective-replay-fixture.py',root],
                     {cwd,encoding:'utf8',timeout:60_000});
assert.equal(make.status,0,make.stderr);
const pageUrl=pathToFileURL(make.stdout.trim()).href;
const browser=await chromium.launch({headless:true});
try {
  for(const viewport of [{width:1280,height:800},{width:390,height:844}]) {
    const page=await browser.newPage({viewport,acceptDownloads:true});
    const errors=[],requests=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>requests.push(r.url()));
    await page.goto(pageUrl);
    await page.locator('#event-list button').first().waitFor();
    assert.equal(await page.locator('#moment option').count(),4);
    assert.equal(await page.locator('#event-list button').count(),1);
    assert.match(await page.locator('#detail').textContent(),/FUTURE NAME/);
    assert.equal(await page.locator('#detail img').count(),0);

    await page.locator('#moment').selectOption('2026-10-12T00:18:00+00:00');
    assert.match(await page.locator('#detail').textContent(),/EARLY/);
    assert.doesNotMatch(await page.locator('#detail').textContent(),/FUTURE NAME/);
    assert.equal(await page.locator('#detail tbody tr').count(),1);
    assert.match(await page.locator('#detail').textContent(),/OC/);

    await page.locator('#moment').selectOption('2026-10-12T06:18:00+00:00');
    assert.match(await page.locator('#detail').textContent(),/source_unavailable/);
    assert.equal(await page.locator('#detail tbody tr').count(),2);

    await page.locator('#moment').selectOption('2026-10-12T12:18:00+00:00');
    assert.match(await page.locator('#detail').textContent(),/not_listed_in_complete_scan/);
    assert.match(await page.locator('#detail').textContent(),/NOT extinguished/);

    await page.locator('#moment').selectOption('2026-10-12T18:18:00+00:00');
    assert.match(await page.locator('#detail').textContent(),/FUTURE NAME/);
    assert.match(await page.locator('#detail').textContent(),/UC/);
    assert.equal(await page.locator('#detail tbody tr').count(),4);

    await page.locator('#find').fill('not-present-in-agency-history');
    assert.equal(await page.locator('#event-list button').count(),0);
    assert.equal(await page.locator('#download').isDisabled(),true);
    await page.locator('#find').fill('');
    const [download]=await Promise.all([
      page.waitForEvent('download'),page.locator('#download').click()
    ]);
    assert.equal(download.suggestedFilename(),'agency-as-of-evidence.json');
    const result=JSON.parse(await readFile(await download.path(),'utf8'));
    assert.equal(result.known_record.trace.length,4);
    assert.equal(result.extinguishment_label,null);
    assert.equal(result.confirmed_nonfire_label,null);
    assert.equal(result.independently_verified_physical_fire_identity,false);
    assert.equal(result.no_future_receipts_included,true);

    assert.deepEqual(errors,[]);
    assert.deepEqual(requests.filter(x=>!x.startsWith('file:')),[]);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false);
    await page.close();
  }
}finally{
  await browser.close();
  await rm(root,{recursive:true,force:true});
}
console.log('Agency receipt decision-time replay: desktop/mobile original-like synthetic source and evidence export passed.');
