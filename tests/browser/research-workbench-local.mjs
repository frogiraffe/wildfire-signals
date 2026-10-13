import assert from 'node:assert/strict';
import {mkdtemp, writeFile, readFile, rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {pathToFileURL} from 'node:url';
import {spawnSync} from 'node:child_process';
import {chromium} from 'playwright';

const tmp = await mkdtemp(join(tmpdir(), 'wildfire-research-e2e-'));
const app = join(tmp, 'research.html');
const project = new URL('../../', import.meta.url).pathname;
const generator = 'tests/browser/generate-research-workbench-fixture.py';
const created = spawnSync('python', [generator, app],
                          {cwd:project,encoding:'utf8',timeout:60_000});
assert.equal(created.status, 0, created.stderr);
const count = Number(created.stdout.trim());
assert.ok(count > 1, 'Source-fixture study should have multiple original cases');
const browser = await chromium.launch({headless:true});
try {
  for (const viewport of [{width:1280,height:800},{width:390,height:844}]) {
    const page = await browser.newPage({viewport,acceptDownloads:true});
    const errors = [], requests = [];
    page.on('pageerror', error=>errors.push(error.message));
    page.on('request', request=>requests.push(request.url()));
    await page.goto(pathToFileURL(app).href);
    await page.locator('#case-list button').first().waitFor();

    assert.equal(await page.locator('#case-list button').count(), count);
    assert.equal((await page.locator('#source-hash').textContent()).length,64);
    assert.match(await page.locator('header').textContent(),
                 /No independently verified physical wildfire identities/);
    assert.match(await page.locator('#visible-count').textContent(),
                 new RegExp('^'+count+' of '+count));

    // Search original researcher-identifiable names, then return to complete queue.
    await page.locator('#search').fill('TEST_FIRE_100');
    assert.ok(await page.locator('#case-list button').count() > 0);
    assert.ok(await page.locator('#case-list button').count() < count);
    await page.locator('#search').fill('does-not-exist-anywhere');
    assert.equal(await page.locator('#case-list button').count(),0);
    assert.match(await page.locator('#case-list').textContent(),/No research cases match/);
    await page.locator('#search').fill('');
    await page.locator('#case-list button').first().click();
    assert.match(await page.locator('#detail').textContent(),
                 /Original CAL FIRE candidate-linked pages/);
    assert.match(await page.locator('#detail').textContent(),
                 /NO independently verified wildfire identity/);
    assert.ok(await page.locator('#detail article.source').count() >= 1);

    const note = 'Investigate another original event source; unverified <img src=x onerror=alert(1)>';
    await page.locator('#detail select').selectOption('blocked');
    await page.locator('#detail textarea').fill(note);
    await page.locator('#work-state').selectOption('blocked');
    assert.equal(await page.locator('#case-list button').count(),1);
    await page.locator('#work-state').selectOption('all');

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#download-session').click(),
    ]);
    assert.equal(download.suggestedFilename(),'private-wildfire-research-session.json');
    const output = JSON.parse(await readFile(await download.path(),'utf8'));
    assert.equal(output.entries.length,count);
    assert.equal(output.status,'private_research_notes_not_wildfire_labels');
    assert.equal(output.source_casebook_sha256.length,64);
    const altered = output.entries.find(entry=>entry.note===note);
    assert.ok(altered);
    assert.equal(altered.work_state,'blocked');

    // Import restores the exact source-bound notes, without executing HTML.
    await page.locator('#detail textarea').fill('temporary unsaved change');
    await page.locator('#session-file').setInputFiles(await download.path());
    await page.locator('#flash').getByText(/session imported/).waitFor();
    assert.equal(await page.locator('#detail textarea').inputValue(),note);
    assert.equal(await page.locator('#detail img').count(),0);

    // A different source fingerprint cannot overwrite the current research notes.
    const wrong = {...output,source_casebook_sha256:'f'.repeat(64)};
    const badPath = join(tmp, 'wrong-source-'+viewport.width+'.json');
    await writeFile(badPath, JSON.stringify(wrong));
    await page.locator('#session-file').setInputFiles(badPath);
    await page.locator('#flash').getByText(/Import rejected/).waitFor();
    assert.equal(await page.locator('#detail textarea').inputValue(),note);

    // E2E CSP + offline contract: no programmatic remote requests, no script errors.
    assert.deepEqual(errors,[]);
    assert.deepEqual(requests.filter(url=>!url.startsWith('file:')),[]);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth+2),false);
    await page.close();
  }
} finally {
  await browser.close();
  await rm(tmp,{recursive:true,force:true});
}
console.log('Offline historical research app: desktop + mobile, all-source replay, CSP, notes export/import and source-lock passed.');
