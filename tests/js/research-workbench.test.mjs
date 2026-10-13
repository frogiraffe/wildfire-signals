import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../../fire_public/research_workbench.js', import.meta.url), 'utf8');
const context = vm.createContext({});
vm.runInContext(source, context);
const api = context.WildfireResearch;

const digest = 'a'.repeat(64);
function book() {
  const make = (id, name, priority, count) => ({
    candidate_id: id, priority_group: priority, priority_order: count,
    next_action: 'Collect independent source records',
    mtbs: {fire_id:'MTBS-'+id, name, retrospective_day:'2018-07-20'},
    nifc: {source_identity:'NIFC-'+id, name:name+' agency'},
    original_official_pages: count === 0 ? [] : [
      {source_url:'https://example.org/'+id, source_name:'CAL FIRE '+name}],
    same_physical_event_verified:false, independent_nonfire_verified:false,
    risk_or_forecast_score:null
  });
  return {
    schema_version:1,
    research_status:'private_historical_investigation_queue_not_ground_truth',
    verified_same_event_crosswalks:0, verified_nonfire_labels:0,
    measured_model_skill:false, no_confirmed_fire_or_nonfire_labels:true,
    source_casebook_sha256:digest,
    original_candidate_population:3,
    rows:[make('cand-a','Alpha Creek','multiple_official_leads',2),
          make('cand-b','Beta Mountain','single_name_lead',1),
          make('cand-c','Gamma','no_name_lead',0)]
  };
}
const values = () => ({'cand-a':{work_state:'investigating',note:'Need original incident ID'},
                       'cand-b':{work_state:'blocked',note:'Agency archive not available'}});

test('never treats private historical source list as validated fire labels', () => {
  assert.equal(api.assertBook(book()).rows.length, 3);
  for (const key of ['verified_same_event_crosswalks','verified_nonfire_labels']) {
    const forged = book(); forged[key] = 1;
    assert.throws(() => api.assertBook(forged), /Unverified/);
  }
  const forged = book(); forged.rows[0].same_physical_event_verified=true;
  assert.throws(() => api.assertBook(forged), /Unsafe/);
  const duplicated = book(); duplicated.rows[1].candidate_id='cand-a';
  assert.throws(() => api.assertBook(duplicated), /duplicate/);
});

test('offline search supports IDs, provider names, originals and work filters', () => {
  assert.deepEqual(Array.from(api.findRows(book(), values(), 'alpha')).map(x=>x.candidate_id), ['cand-a']);
  assert.deepEqual(Array.from(api.findRows(book(), values(), 'NIFC-cand-b')).map(x=>x.candidate_id), ['cand-b']);
  assert.deepEqual(Array.from(api.findRows(book(), values(), '', 'all', 'blocked')).map(x=>x.candidate_id), ['cand-b']);
  assert.deepEqual(Array.from(api.findRows(book(), values(), '', 'no_name_lead')).map(x=>x.candidate_id), ['cand-c']);
  assert.deepEqual(Array.from(api.findRows(book(), values(), 'zebra')).map(x=>x.candidate_id), []);
  assert.equal(api.findRows(book(), values()).length, 3);
});

test('notes session is hash-locked, bounded and cannot contain verified fire states', () => {
  const stamp='2026-10-13T10:00:00.000Z';
  const session = api.makeSession(book(), values(), stamp);
  assert.equal(session.entries.length, 3);
  assert.equal(session.entries[2].work_state, 'not_started');
  assert.equal(session.entries[2].note, '');
  assert.equal(api.validateSession(session,book())['cand-a'].note, 'Need original incident ID');
  assert.equal(session.status, 'private_research_notes_not_wildfire_labels');
  assert.equal(JSON.stringify(session).includes('risk_score'), false);
  const foreign = structuredClone(session); foreign.source_casebook_sha256='b'.repeat(64);
  assert.throws(()=>api.validateSession(foreign,book()),/fingerprint/);
  const wrong = structuredClone(session); wrong.entries[0].work_state='verified_fire';
  assert.throws(()=>api.validateSession(wrong,book()),/unsupported/);
  const duplicate = structuredClone(session); duplicate.entries[1].candidate_id='cand-a';
  assert.throws(()=>api.validateSession(duplicate,book()),/duplicate/);
  const unknown = structuredClone(session); unknown.entries[0].candidate_id='unknown';
  assert.throws(()=>api.validateSession(unknown,book()),/Unknown case/);
  const oversized = structuredClone(session); oversized.entries[0].note='X'.repeat(3001);
  assert.throws(()=>api.validateSession(oversized,book()),/unsupported/);
  const injected = structuredClone(session); injected.verified_same_fire=true;
  assert.throws(()=>api.validateSession(injected,book()),/schema/);
});

test('no silent persistence/network APIs in shipped source', () => {
  assert.doesNotMatch(source,/localStorage|sessionStorage|indexedDB|fetch\s*\(/);
  assert.doesNotMatch(source,/XMLHttpRequest|WebSocket|serviceWorker/);
  assert.match(source,/URL\.createObjectURL/);
  assert.match(source,/file\.text\(\)/);
  assert.match(source,/textContent/);
  assert.match(source,/noopener noreferrer/);
});
