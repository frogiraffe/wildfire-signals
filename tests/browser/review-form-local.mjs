import assert from 'node:assert/strict';
import {mkdtemp,writeFile,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {chromium} from 'playwright';

const dir=await mkdtemp(join(tmpdir(),'wildfire-private-review-'));
const queue=join(dir,'queue.json');
const html=join(dir,'private-review.html');
const source={
  schema_version:1,state:'unadjudicated_review_queue',
  cases:[
    {case_id:'official:2018:77',
     kind:'retrospective_official_perimeter_review',
     source_fire_year:2018,source_object_id:77,
     source_name:"</script><img src=x onerror=alert('xss')>",
     proposed_label:null},
    {case_id:'frame:unknown-1',kind:'independent_frame_review',
     region_id:'unit-1',latitude:37.02,longitude:-120.1,
     decision_at:'2018-07-01T12:00:00Z',proposed_label:null},
  ]
};
await writeFile(queue,JSON.stringify(source));
const run=spawnSync('python',['-m','fire_public.review_form',
  '--queue',queue,'--reviewer-id','researcher-one','--html',html],
  {cwd:new URL('../../',import.meta.url).pathname,encoding:'utf8'});
assert.equal(run.status,0,run.stderr);
const browser=await chromium.launch({headless:true});
try{
  for(const viewport of [{width:1280,height:800},{width:390,height:844}]){
    const page=await browser.newPage({viewport,acceptDownloads:true});
    const errors=[];
    const requests=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('request',r=>requests.push(r.url()));
    await page.goto(pathToFileURL(html).href);
    await page.locator('article').first().waitFor();
    assert.equal(await page.locator('article').count(),2);
    assert.equal(await page.locator('#count').textContent(),'2');
    assert.match(await page.locator('article').first().textContent(),/<\/script>/);
    assert.equal(await page.locator('article').first().locator('img').count(),0);
    assert.deepEqual(await page.locator('article').first()
      .locator('select option').allTextContents(),[
      'Not reviewed','Positive: independently supported fire',
      'Abstain / insufficient evidence'
    ]);
    await page.locator('#export').click();
    assert.match(await page.locator('#errors').textContent(),/Case 1/);
    assert.match(await page.locator('#errors').textContent(),/Case 2/);
    const first=page.locator('article').nth(0);
    await first.locator('select').selectOption('vote1');
    await first.locator('input[type=text]').first().fill('http://not-https.example');
    await first.locator('input[type=checkbox]').check();
    await page.locator('article').nth(1).locator('select').selectOption('abstain');
    await page.locator('article').nth(1).locator('input[type=text]').last().fill(
      'Unable to find independent full-window source coverage');
    await page.locator('#export').click();
    assert.match(await page.locator('#errors').textContent(),/HTTPS evidence/);
    await first.locator('input[type=text]').first().fill('https://example.org/official/77');
    const [download]=await Promise.all([
      page.waitForEvent('download'),
      page.locator('#export').click(),
    ]);
    assert.equal(download.suggestedFilename(),'wildfire-votes-researcher-one.json');
    const result=JSON.parse(await readFile(await download.path(),'utf8'));
    assert.equal(result.reviewer_id,'researcher-one');
    assert.equal(result.queue_sha256.length,64);
    assert.deepEqual(result.votes.map(v=>v.status),['vote','abstain']);
    assert.deepEqual(result.votes.map(v=>v.reviewer_label),[1,undefined]);
    assert.equal(result.votes[0].independent_evidence_checked,true);
    assert.equal(result.votes[0].evidence_url,'https://example.org/official/77');
    assert.match(result.votes[0].reviewed_at,/Z$/);
    assert.match(result.votes[1].reason,/independent/);
    assert.equal(requests.filter(x=>!x.startsWith('file:')).length,0);
    assert.deepEqual(errors,[]);
    await page.close();
  }
}finally{
  await browser.close();
  await rm(dir,{recursive:true,force:true});
}
console.log('Standalone blind review: desktop+mobile, CSP, validation, JSON export passed.');
