import test from 'node:test';
import assert from 'node:assert/strict';
import {parseState,stateHash,visible,effectiveStatus,featureCollection} from '../../public/map-state.mjs';

test('URL view round trips and invalid input is bounded', () => {
  const state = parseState('#lang=tr&hours=6&source=firms&kind=candidate&lat=35&lon=30&zoom=8');
  assert.deepEqual(parseState(stateHash(state)),state);
  assert.equal(parseState('#zoom=Infinity&hours=15&lat=900').zoom,3);
  assert.equal(parseState('#zoom=Infinity&hours=15&lat=900').hours,24);
  assert.equal(parseState('#lat=900').lat,85);
});

test('time, source and record type filters stay separate', () => {
  const now = new Date('2026-10-09T12:00:00Z');
  const snapshot = {events:[
    {event_id:'new',observed_at:'2026-10-09T11:00:00Z',sources:['firms']},
    {event_id:'old',observed_at:'2026-10-07T11:00:00Z',sources:['firms']}],
  incidents:[{official_id:'n1',provider:'nifc',last_seen_at:'2026-10-09T11:00:00Z'}]};
  const state = {...parseState(),hours:24,source:'firms',kind:'all'};
  assert.deepEqual(visible(snapshot,state,now).events.map(x => x.event_id),['new']);
  state.hours = 72;
  assert.deepEqual(visible(snapshot,state,now).events.map(x => x.event_id),['new','old']);
  assert.equal(visible(snapshot,state,now).incidents.length,0);
  state.source = 'all'; state.kind = 'incident';
  assert.equal(visible(snapshot,state,now).events.length,0);
  assert.equal(visible(snapshot,state,now).incidents.length,1);
  state.hours = 6;
  snapshot.incidents[0].last_seen_at = '2026-10-08T12:00:00Z';
  assert.equal(visible(snapshot,state,now).incidents.length,1);
});

test('map feature retains kind for selected record', () => {
  const result = featureCollection([{event_id:'e1',latitude:36,longitude:30}],'candidate');
  assert.deepEqual(result.features[0].geometry.coordinates,[30,36]);
  assert.equal(result.features[0].properties.kind,'candidate');
});

test('previously fresh snapshot becomes stale when collection stops', () => {
  const manifest = {last_scan_at:'2026-10-09T12:00:00Z',data_status:'fresh'};
  assert.equal(effectiveStatus(manifest,new Date('2026-10-09T12:20:00Z')),'fresh');
  assert.equal(effectiveStatus(manifest,new Date('2026-10-09T14:00:00Z')),'stale');
  assert.equal(effectiveStatus({},new Date('2026-10-09T12:00:00Z')),'unknown');
});
