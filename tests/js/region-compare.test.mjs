import test from 'node:test';
import assert from 'node:assert/strict';
import {compareRegions} from '../../public/region-compare.mjs';
import {parseState,stateHash} from '../../public/map-state.mjs';

const now=new Date('2026-10-12T12:00:00Z');
const a={latitude:0,longitude:179.9,radiusKm:25};
const b={latitude:0,longitude:178,radiusKm:25};
const record=(id,hoursAgo,longitude,source='VIIRS_NOAA20_NRT')=>({
  kind:'satellite_candidate',event_id:id,latitude:0,longitude,
  observed_at:new Date(now.getTime()-hoursAgo*3_600_000).toISOString(),
  received_at:new Date(now.getTime()-hoursAgo*3_600_000+60_000).toISOString(),
  sources:[source]
});
const snapshot=(rows,other={})=>({
  manifest:{schema_version:1,last_scan_at:now.toISOString(),data_status:'fresh',...other.manifest},
  events:rows,incidents:[],sources:other.sources||[
    {key:'VIIRS_NOAA20_NRT',status:'complete'},
    {key:'VIIRS_NOAA21_NRT',status:'complete'},
    {key:'nifc_wfigs',status:'complete'},
    {key:'cwfis',status:'complete'}
  ]
});
test('Different worldwide circles use same radius/source/time and do not count unrelated geography',()=>{
  const data=snapshot([
    record('a-1',1,-179.95), record('a-2',2,-179.95),
    record('b-1',3,178),record('outside',1,0),
    record('future',-1,178),record('old',26,178)
  ]);
  const result=compareRegions(data,a,b,{now,hours:24});
  assert.equal(result.status,'descriptive_thermal_comparison_only');
  assert.equal(result.first.candidateCellHours,2);
  assert.equal(result.second.candidateCellHours,1);
  assert.equal(result.differenceCellHours,1);
  assert.equal(result.sameObservationWindow,true);
  assert.equal(result.sameRadiusKm,25);
  assert.equal(result.areasOverlap,false);
  assert.equal(result.first.distinctCells,1);
  assert.equal(result.independentlyVerifiedFireDifference,null);
  assert.equal(result.wildfireRiskRankingAvailable,false);
  assert.equal(result.comparableAcquisitionCoverageVerified,false);
  assert.equal(result.sourceEvidence.first.confirmedFireCoverageVerified,false);
  assert.ok(result.centerSeparationKm>180);
  assert.ok(result.sensorMemberships.some(x=>x.key==='VIIRS_NOAA20_NRT'&&x.first===2&&x.second===1));
});

test('Overlapping circles retain the shared source count and do not claim two independent events',()=>{
  const data=snapshot([record('overlap',1,179.95)]);
  const x=compareRegions(data,a,{latitude:0,longitude:179.96,radiusKm:25},{now});
  assert.equal(x.areasOverlap,true);
  assert.equal(x.status,'overlapping_areas');
  assert.equal(x.first.candidateCellHours,1);
  assert.equal(x.second.candidateCellHours,1);
  assert.equal(x.differenceCellHours,0);
  assert.match(x.limitations.join(' '),/overlap/);
  assert.equal(x.fireAbsenceInEitherRegionVerified,false);
});

test('No snapshot, stale source, partial source, and truncated source block clean evidence claims',()=>{
  const data=snapshot([record('one',1,179.9)]);
  const missing=compareRegions(snapshot([], {manifest:{last_scan_at:null}}),a,b,{now});
  assert.equal(missing.status,'unavailable');
  assert.equal(missing.first.candidateCellHours,null);
  assert.equal(missing.differenceCellHours,null);
  const stale=compareRegions(snapshot([record('one',5,179.9)],{manifest:{
    last_scan_at:new Date(now.getTime()-3*3_600_000).toISOString()}}),a,b,{now});
  assert.equal(stale.status,'incomplete_source_evidence');
  assert.equal(stale.first.candidateCellHours,0); // Observed after snapshot cannot be seen.
  const failed=compareRegions(snapshot([record('one',1,179.9)],{sources:[
    {key:'VIIRS_NOAA20_NRT',status:'failed'}]}),a,b,{now});
  assert.equal(failed.status,'incomplete_source_evidence');
  assert.equal(failed.sourceEvidence.first.rows.find(s=>s.key==='VIIRS_NOAA20_NRT').status,'failed');
  const partial=compareRegions(snapshot([], {manifest:{truncated:true}}),a,b,{now});
  assert.equal(partial.status,'descriptive_thermal_comparison_only');
  assert.ok(partial.limitations.some(s=>s.includes('truncated')));
  assert.equal(partial.sourceEvidence.first.snapshotTruncated,true);
  assert.equal(partial.wildfireRiskRankingAvailable,false);
  assert.equal(data.manifest.data_status,'fresh');
});

test('Agency-only filter cannot manufacture a meaningful satellite zero',()=>{
  const result=compareRegions(snapshot([record('a',1,179.9)]),a,b,{now,source:'nifc_wfigs'});
  assert.equal(result.status,'unsupported_source_filter');
  assert.equal(result.first.candidateCellHours,null);
  assert.equal(result.second.candidateCellHours,null);
  assert.equal(result.differenceCellHours,null);
  assert.match(result.limitations.join(' '),/excludes satellite/);
});

test('Invalid unequal radius, coordinates, UTC window and time refuse comparisons',()=>{
  const data=snapshot([]);
  assert.throws(()=>compareRegions(data,a,{...b,radiusKm:50},{now}),RangeError);
  assert.throws(()=>compareRegions(data,a,{...b,latitude:95},{now}),RangeError);
  assert.throws(()=>compareRegions(data,a,b,{now,hours:12}),RangeError);
  assert.throws(()=>compareRegions(data,a,b,{now:new Date('invalid')}),RangeError);
});

test('A and B comparison positions round-trip on worldwide share URL and clear without A',()=>{
  const state=parseState('#lang=tr&hours=72&lat=12&lon=175&zoom=4&rlat=12.5&rlon=179.9&rr=100&clat=-12.5&clon=-179.8');
  assert.equal(state.compareLat,-12.5);
  assert.equal(state.compareLon,-179.8);
  assert.deepEqual(parseState(stateHash(state)),state);
  const noA=parseState('#clat=12&clon=60&rr=50');
  assert.equal(noA.compareLat,null);
  assert.equal(noA.compareLon,null);
  const clear={...state,compareLat:null,compareLon:null};
  assert.doesNotMatch(stateHash(clear),/clat|clon/);
  assert.ok(stateHash(clear).includes('rlat='));
  const bothClear={...state,regionLat:null,regionLon:null};
  assert.doesNotMatch(stateHash(bothClear),/clat|clon|rlat|rlon/);
});
