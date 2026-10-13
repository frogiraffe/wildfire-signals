import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const js=fs.readFileSync(new URL('../../fire_public/prospective_replay.js',import.meta.url),'utf8');
const context=vm.createContext({});
vm.runInContext(js,context);
const api=context.AgencyReplay;
const t0='2026-10-12T00:18:00+00:00';
const t1='2026-10-12T06:18:00+00:00';
const t2='2026-10-12T12:18:00+00:00';
const t3='2026-10-12T18:18:00+00:00';
const stamp=time=>time.replace('18:','17:');
const scan=(time,status)=>({
  scan_at:stamp(time),captured_at:time,run_id:'100',
  provider:'cwfis',status,snapshot_key:'snapshot:'+'a'.repeat(64),
  receipt_sha256:'b'.repeat(64)
});
function book() {
  const scans=[scan(t0,'complete'),scan(t1,'failed'),
               scan(t2,'complete'),scan(t3,'complete')];
  const base=(time,availability,agencyStatus,name)=>({
    scan_at:stamp(time),captured_at:time,
    source_status:availability==='source_unavailable'?'failed':'complete',
    availability,agency_status:agencyStatus,source_name:name,
    receipt_sha256:'b'.repeat(64),observation_sha256:
      availability==='listed'?'c'.repeat(64):null,
    extinguishment_label:null,event_identity_independently_verified:false
  });
  const first={
    provider:'cwfis',official_id:'CAN-A',
    source_identity:JSON.stringify(['cwfis','CAN-A']),
    latest_known_name:'FUTURE NAME',
    physical_fire_identity_verified:false,verified_extinguishment_at:null,
    verified_nonfire:false,
    timeline:[
      base(t0,'listed','OC','OLD NAME'),
      base(t1,'source_unavailable',null,null),
      base(t2,'not_listed_in_complete_scan',null,null),
      base(t3,'listed','UC','FUTURE NAME')
    ]
  };
  const next={...first,official_id:'CAN-B',source_identity:JSON.stringify(['cwfis','CAN-B']),
    latest_known_name:'LATE ONLY',
    timeline:[base(t0,'not_listed_in_complete_scan',null,null),
      base(t1,'source_unavailable',null,null),
      base(t2,'not_listed_in_complete_scan',null,null),
      base(t3,'listed','OC','LATE ONLY')]};
  return {
    schema_version:1,research_status:'source_bound_prospective_agency_timeline_not_fire_outcome',
    as_of:'2026-10-12T23:00:00+00:00',known_source_identities:2,
    agency_scan_count:4,scans,cases:[first,next],
    verified_cross_provider_event_links:0,verified_nonfire_labels:0,
    verified_extinguishment_labels:0,forecast_skill_measured:false
  };
}

test('rewinding hides future agency identities, names and changing statuses',()=>{
  const early=api.stateAt(book(),'2026-10-12T03:00:00Z');
  assert.equal(early.rows.length,1);
  assert.equal(early.rows[0].name,'OLD NAME');
  assert.equal(early.rows[0].agencyStatus,'OC');
  assert.equal(early.rows[0].trace.length,1);
  assert.equal(early.verifiedWildfireCount,null);
  const failed=api.stateAt(book(),'2026-10-12T09:00:00Z');
  assert.equal(failed.rows.length,1);
  assert.equal(failed.rows[0].availability,'source_unavailable');
  assert.equal(failed.rows[0].agencyStatus,null);
  const disappeared=api.stateAt(book(),'2026-10-12T15:00:00Z');
  assert.equal(disappeared.rows[0].availability,'not_listed_in_complete_scan');
  assert.equal(disappeared.rows[0].name,'OLD NAME');
  const late=api.stateAt(book(),'2026-10-12T21:00:00Z');
  assert.equal(late.rows.length,2);
  assert.equal(late.rows[0].name,'FUTURE NAME');
  assert.equal(late.rows[0].agencyStatus,'UC');
  assert.equal(late.rows[1].name,'LATE ONLY');
});

test('source-scoped as-of export is not a fire outcome or forward-looking receipt',()=>{
  const early=api.excerpt(book(),'2026-10-12T03:00:00Z',JSON.stringify(['cwfis','CAN-A']));
  assert.equal(early.known_record.trace.length,1);
  assert.equal(early.known_record.name,'OLD NAME');
  assert.equal(early.extinguishment_label,null);
  assert.equal(early.confirmed_nonfire_label,null);
  assert.equal(early.no_future_receipts_included,true);
  assert.equal(early.independently_verified_physical_fire_identity,false);
  assert.throws(()=>
    api.excerpt(book(),'2026-10-12T03:00:00Z',JSON.stringify(['cwfis','CAN-B'])),
    /not known/);
  assert.throws(()=>
    api.stateAt(book(),'2026-10-13T01:00:00Z'),/beyond/);
});

test('source identity search respects only currently known names and providers',()=>{
  const early=api.stateAt(book(),'2026-10-12T03:00:00Z','future');
  assert.equal(early.rows.length,0);
  assert.equal(api.stateAt(book(),'2026-10-12T03:00:00Z','can-a').rows.length,1);
  assert.equal(api.stateAt(book(),'2026-10-12T21:00:00Z','future').rows.length,1);
  assert.equal(api.stateAt(book(),'2026-10-12T21:00:00Z','nifc').rows.length,0);
});

test('falsified labels and contradictory source states reject before render',()=>{
  const forged=book();forged.verified_extinguishment_labels=1;
  assert.throws(()=>api.assertBook(forged),/Source-bound/);
  const fake=book();fake.cases[0].physical_fire_identity_verified=true;
  assert.throws(()=>api.assertBook(fake),/Duplicate, fabricated/);
  const bad=book();bad.cases[0].timeline[1].source_status='complete';
  assert.throws(()=>api.assertBook(bad),/Unsupported/);
  const duplicate=book();duplicate.cases[1].official_id='CAN-A';
  assert.throws(()=>api.assertBook(duplicate),/Duplicate/);
});

test('offline script creates downloads only from explicit action and has no network APIs',()=>{
  assert.doesNotMatch(js,/fetch\s*\(|XMLHttpRequest|WebSocket|localStorage|sessionStorage|indexedDB/);
  assert.match(js,/textContent/);
  assert.match(js,/URL\.createObjectURL/);
  assert.match(js,/source identities known at this captured moment/);
});
