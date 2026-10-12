import test from 'node:test';
import assert from 'node:assert/strict';
import {gzipSync} from 'node:zlib';
import {onRequestGet as events} from '../../functions/api/v2/events.js';
import {onRequestGet as dossier} from '../../functions/api/v2/events/[id].js';
import {onRequestGet as sources} from '../../functions/api/v2/sources.js';
import {onRequestGet as run} from '../../functions/api/v2/runs/[id].js';

const snapshot = {manifest:{schema_version:1,generated_at:'2026-10-12T12:00:00Z',data_status:'partial'},
  events:[{kind:'satellite_candidate',event_id:'firms-abc',latitude:1,longitude:2,
    observed_at:'2026-10-12T11:00:00Z',detection_count:2}],
  incidents:[{kind:'agency_incident',provider:'nifc_wfigs',official_id:'A/B',name:'Test',
    latitude:1,longitude:2,modified_at:'2026-10-12T10:00:00Z'}],
  sources:[{key:'VIIRS_NOAA20_NRT',status:'failed',last_success_at:null}],
  details:{incident_history:{'nifc_wfigs:A/B':[{change:'first_seen',seen_at:'2026-10-12T11:00:00Z'}]}}};
function context(url='https://example.test/api/v2/events', id='') {
  const payload=gzipSync(JSON.stringify(snapshot));
  const env={PUBLIC_SNAPSHOTS:{get:async (key)=>key==='current'
    ? {key:'snapshot:'+'a'.repeat(64)} : key==='snapshot:'+'a'.repeat(64) ? payload : null}};
  return {env,request:new Request(url),params:{id}};
}

test('event list is bounded and keeps candidates separate from agency records',async()=>{
  const response=await events(context('https://example.test/api/v2/events?limit=1'));
  assert.equal(response.status,200);
  const body=await response.json();
  assert.equal(body.events.length,1);
  assert.equal(body.next_offset,1);
  assert.equal(body.events[0].kind,'satellite_candidate');
  assert.equal(body.data_status,'partial');
  assert.equal(body.events[0].area_km2,undefined);
});

test('dossier uses exact agency identity and marks unsupported outcomes unknown',async()=>{
  const response=await dossier(context('https://example.test/api/v2/events/nifc_wfigs%3AA%2FB','nifc_wfigs:A/B'));
  assert.equal(response.status,200);
  const body=await response.json();
  assert.equal(body.id,'nifc_wfigs:A/B');
  assert.equal(body.observations[0].kind,'agency_incident');
  assert.equal(body.area_history.status,'unavailable');
  assert.equal(body.forecast_runs.length,0);
  assert.equal(body.outcomes.growth_stopped,'unknown');
  assert.equal(body.history.length,1);
});

test('sources expose failures and unavailable runs never invent forecasts',async()=>{
  const sourceResponse=await sources(context());
  assert.equal((await sourceResponse.json()).sources[0].status,'failed');
  const runResponse=await run(context('https://example.test/api/v2/runs/test','test'));
  assert.equal(runResponse.status,404);
  assert.equal((await runResponse.json()).error,'forecast_run_unavailable');
});

test('malformed query and missing snapshot fail closed',async()=>{
  assert.equal((await events(context('https://example.test/api/v2/events?limit=1000000'))).status,400);
  const ctx=context(); ctx.env.PUBLIC_SNAPSHOTS.get=async()=>null;
  const response=await events(ctx);
  assert.equal(response.status,503);
  assert.equal((await response.json()).error,'snapshot_unavailable');
});
