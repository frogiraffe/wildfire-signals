import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {chromium} from 'playwright';

const base=fileURLToPath(new URL('../../',import.meta.url));
const root=await mkdtemp(join(tmpdir(),'wildfire-pair-review-'));
const study=join(root,'aligned');
const packet=join(root,'offline-pair-review.html');
const inlinePython=[
  'import sys',
  'from pathlib import Path',
  "sys.path.insert(0,'tests')",
  'from test_mtbs_region_study import SharedRegionStudyTests',
  'from fire_public.mtbs_region_study import write_capture',
  'fixture=SharedRegionStudyTests("test_queries_use_identical_region_and_year_before_selection")',
  'fixture.setUp()',
  'report,files=fixture.study()',
  'write_capture(Path(sys.argv[1]),report,files)',
  'fixture.doCleanups()'
].join('\n');
const create=spawnSync('python',['-c',inlinePython,study],{cwd:base,encoding:'utf8'});
assert.equal(create.status,0,create.stderr);
const process=spawnSync('python',['-m','fire_public.mtbs_match_review',
  'packet','--study-dir',study,'--reviewer-id','reviewer-one','--html',packet],
  {cwd:base,encoding:'utf8'});
assert.equal(process.status,0,process.stderr);
const browser=await chromium.launch({headless:true});
try{
  for (const viewport of [{width:1280,height:800},{width:390,height:844}]) {
    const page=await browser.newPage({viewport,acceptDownloads:true});
    const errors=[],requests=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>requests.push(r.url()));
    await page.goto(pathToFileURL(packet).href);
    await page.locator('#position').waitFor();
    const initial=await page.locator('#position').textContent();
    assert.match(initial,/Candidate 1 of [2-9]/);
    assert.match(await page.locator('#nifc').textContent(),/NIFC perimeter #/);
    assert.match(await page.locator('#mtbs').textContent(),/MTBS #/);
    assert.equal(await page.locator('svg path').count()>0,true);
    assert.equal(await page.locator('svg circle').count(),1);
    assert.match(await page.locator('#date').textContent(),/2018/);
    const count=Number((initial.match(/of (\d+)/)||[])[1]);
    assert.ok(count>=2);
    await page.locator('#export').click();
    assert.match(await page.locator('#errors').textContent(),/Candidate 1/);
    assert.match(await page.locator('#status').textContent(),/No review exported/);

    for(let i=0;i<count;i++){
      const decision = i===0 ? 'same_event_hypothesis' : 'inconclusive';
      await page.locator('#decision').selectOption(decision);
      await page.locator('#reason').fill('Researched provider record and geography, still not confirmed.');
      if(i===0){
        await page.locator('#evidence').fill('http://unsafe.example/case');
        await page.locator('#export').click();
        assert.match(await page.locator('#errors').textContent(),/HTTPS/);
        await page.locator('#evidence').fill('https://example.org/independent/source-record');
      }
      if(i<count-1){
        await page.locator('#next').click();
      }
    }
    assert.equal(await page.locator('#next').isDisabled(),true);
    const [download]=await Promise.all([
      page.waitForEvent('download'),
      page.locator('#export').click()
    ]);
    assert.equal(download.suggestedFilename(),'mtbs-nifc-pair-review-reviewer-one.json');
    const votes=JSON.parse(await readFile(await download.path(),'utf8'));
    assert.equal(votes.votes.length,count);
    assert.equal(votes.votes[0].decision,'same_event_hypothesis');
    assert.equal(votes.votes[1].decision,'inconclusive');
    assert.equal(votes.classifications_are_unverified_hypotheses,true);
    assert.equal(votes.source_bundle_sha256.length,64);
    const verify=spawnSync('python',['-m','fire_public.mtbs_match_review',
      'validate','--study-dir',study,'--votes',await download.path(),
      '--output',join(root,'audit-'+viewport.width+'.json')],
      {cwd:base,encoding:'utf8'});
    assert.equal(verify.status,0,verify.stderr);
    assert.equal(requests.filter(url=>!url.startsWith('file:')).length,0);
    assert.deepEqual(errors,[]);
    await page.close();
  }
} finally {
  await browser.close();
  await rm(root,{recursive:true,force:true});
}
console.log('Offline MTBS–NIFC pair review desktop/mobile, SVG, CSP, JSON download and Python validation passed.');
