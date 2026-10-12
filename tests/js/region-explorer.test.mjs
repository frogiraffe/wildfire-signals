import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzeRegion,circleBoundary,distanceKm,normalLongitude,validRegion}
  from '../../public/region-explorer.mjs';
import {parseState,stateHash} from '../../public/map-state.mjs';

const now = new Date('2026-10-12T12:00:00Z');
const region = {latitude:0,longitude:179.9,radiusKm:50};
const event = (id,hoursAgo,lon=179.9,source='VIIRS_NOAA20_NRT',lat=0) => ({
  event_id:id,latitude:lat,longitude:lon,
  observed_at:new Date(now.getTime()-hoursAgo*3_600_000).toISOString(),sources:[source]
});
const snapshot = (events,opts={}) => ({
  manifest:{last_scan_at:now.toISOString(),data_status:'fresh',...opts.manifest},
  events,sources:opts.sources ?? [
    {key:'VIIRS_NOAA20_NRT',status:'complete'},
    {key:'VIIRS_NOAA21_NRT',status:'complete'}]
});

test('Worldwide distance crosses antimeridian and does not find antipodal cells nearby',()=>{
  assert.ok(distanceKm(0,179.9,0,-179.9)<25);
  assert.ok(distanceKm(0,179.9,0,0)>10000);
  assert.equal(normalLongitude(180),-180);
  assert.ok(validRegion(region));
  assert.equal(validRegion({...region,radiusKm:300}),false);
});

test('Circle outline has no map-spanning antimeridian line segment',()=>{
  const feature = circleBoundary(region,120);
  assert.equal(feature.features[0].geometry.type,'MultiLineString');
  const segments=feature.features[0].geometry.coordinates;
  assert.ok(segments.length>=2);
  for (const line of segments) {
    for (let i=1;i<line.length;i++)
      assert.ok(Math.abs(line[i][0]-line[i-1][0])<=180);
  }
  assert.throws(()=>circleBoundary({...region,radiusKm:-1}),RangeError);
  assert.throws(()=>circleBoundary(region,3),RangeError);
});

test('Tracks distinct cell-hours, independent sensor memberships and chronology',()=>{
  const sameCell = [
    event('a',2,-179.9),event('a2',2,-179.9,'VIIRS_NOAA21_NRT'),
    event('b',8,-179.9),event('c',10,170),
    event('d',30,-179.9),event('future',-1,-179.9)];
  const r=analyzeRegion(snapshot(sameCell),region,24,'all',now);
  assert.equal(r.candidateCellHours,2);
  assert.equal(r.distinctCells,1);
  assert.equal(r.recurringCells,2 > 1 ? 1 : 0);
  assert.deepEqual(r.bins.map(b=>b.count),[0,0,0,1,0,1]);
  assert.equal(r.leads[0].observedHours,2);
  assert.equal(r.leads[0].eventId,'a');
  assert.equal(r.sensors.length,2);
  assert.equal(r.quality,'current');
  assert.ok(r.latestObservedAt);
});

test('Source filters and exactly bounded observation windows',()=>{
  const rows=[event('noaa20',2),event('noaa21',5,179.9,'VIIRS_NOAA21_NRT'),
    event('old',23.9), event('too-old',72.1),event('outside',3,178)];
  const data=snapshot(rows);
  assert.equal(analyzeRegion(data,region,6,'VIIRS_NOAA20_NRT',now).candidateCellHours,1);
  assert.equal(analyzeRegion(data,region,24,'all',now).candidateCellHours,3);
  assert.equal(analyzeRegion(data,region,72,'all',now).candidateCellHours,3);
  assert.equal(analyzeRegion(data,region,24,'nifc_wfigs',now).candidateCellHours,0);
});

test('Stale, partial, and unavailable data cannot be presented as complete',()=>{
  const stale=snapshot([event('a',5)],{manifest:{last_scan_at:
    new Date(now.getTime()-3*3_600_000).toISOString()}});
  assert.equal(analyzeRegion(stale,region,24,'all',now).quality,'stale');
  const partial=snapshot([event('a',2)],{sources:[{key:'VIIRS_NOAA20_NRT',status:'failed'}]});
  assert.equal(analyzeRegion(partial,region,24,'all',now).quality,'partial');
  const unavailable=snapshot([event('a',2)],{manifest:{last_scan_at:null}});
  const r=analyzeRegion(unavailable,region,24,'all',now);
  assert.equal(r.quality,'unavailable');
  assert.equal(r.available,false);
  assert.equal(r.candidateCellHours,0);
});

test('Future-of-snapshot observation excluded even when inside current window',()=>{
  const data=snapshot([event('one',1)],{manifest:{last_scan_at:
    new Date(now.getTime()-2*3_600_000).toISOString()}});
  assert.equal(analyzeRegion(data,region,24,'all',now).candidateCellHours,0);
});

test('No observation is not evidence of no wildfire',()=>{
  const r=analyzeRegion(snapshot([]),region,6,'all',now);
  assert.equal(r.candidateCellHours,0);
  assert.equal(r.latestObservedAt,null);
  assert.equal(r.leads.length,0);
});

test('Shareable URL round trips global center and radius; absent selection remains absent',()=>{
  const state=parseState('#lang=tr&hours=72&lat=32&lon=175&zoom=4&rlat=-12.5&rlon=179.9&rr=100');
  assert.deepEqual(parseState(stateHash(state)),state);
  assert.equal(state.radiusKm,100);
  assert.equal(state.regionLon,179.9);
  const cleared={...state,regionLat:null,regionLon:null};
  assert.equal(parseState(stateHash(cleared)).regionLat,null);
  assert.equal(parseState(stateHash(cleared)).regionLon,null);
  assert.ok(!stateHash(cleared).includes('rlat'));
});
