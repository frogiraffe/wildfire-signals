import test from 'node:test';
import assert from 'node:assert/strict';
import {COVERAGE_SOURCES,regionCoverageAudit} from '../../public/coverage-audit.mjs';

const now=new Date('2026-10-12T18:00:00Z');
const scan=now.toISOString();
const circle={latitude:0,longitude:179.9,radiusKm:50};
const observed=new Date(now.getTime()-2*3_600_000).toISOString();
const candidate=(id,lon=179.9,source='VIIRS_NOAA20_NRT',age=observed)=>({
  kind:'satellite_candidate',event_id:id,latitude:0,longitude:lon,
  observed_at:age,received_at:new Date(now.getTime()-3_600_000/2).toISOString(),
  sources:[source]
});
const incident=(provider,id,lon=179.9)=>({
  kind:'agency_incident',provider,official_id:id,latitude:0,longitude:lon,
  modified_at:observed
});
const snap=(updates={})=>({
  manifest:{last_scan_at:scan,data_status:'fresh',schema_version:1},
  sources:[
    {key:'VIIRS_NOAA20_NRT',status:'complete',product_age_seconds:100,
      consecutive_failures:0,last_success_at:scan},
    {key:'VIIRS_NOAA21_NRT',status:'complete'},
    {key:'nifc_wfigs',status:'complete'},
    {key:'cwfis',status:'complete'}
  ],
  events:[candidate('a',-179.9),candidate('b',179.9,'VIIRS_NOAA21_NRT')],
  incidents:[incident('nifc_wfigs','us1',-179.9),incident('cwfis','ca1',179.9)],
  ...updates
});
const audit=(s,region=circle,hours=72)=>regionCoverageAudit(s,region,{hours,now});
const row=(result,key)=>result.rows.find(r=>r.key===key);

test('Versioned source registry declares evidence roles, jurisdictions and reference links',()=>{
  assert.equal(COVERAGE_SOURCES.length,6);
  assert.equal(new Set(COVERAGE_SOURCES.map(x=>x.key)).size,6);
  for (const item of COVERAGE_SOURCES) {
    assert.match(item.url,/^https:\/\//);
    assert.match(item.license,/^https:\/\//);
  }
  assert.equal(COVERAGE_SOURCES.find(s=>s.key==='nifc_wfigs').scope,'us_agency');
  assert.equal(COVERAGE_SOURCES.find(s=>s.key==='cwfis').scope,'canada_agency');
});

test('Antimeridian region audits distinguish satellite candidates from agency layer',()=>{
  const result=audit(snap());
  assert.equal(result.snapshotState,'current');
  assert.equal(row(result,'VIIRS_NOAA20_NRT').observedInCircle,1);
  assert.equal(row(result,'VIIRS_NOAA21_NRT').observedInCircle,1);
  assert.equal(row(result,'nifc_wfigs').observedInCircle,1);
  assert.equal(row(result,'cwfis').observedInCircle,1);
  assert.equal(row(result,'VIIRS_NOAA20_NRT').productAgeSeconds,100);
  assert.equal(row(result,'VIIRS_NOAA20_NRT').status,'complete_request');
  assert.equal(result.region.geometry,'geodesic_circle_not_country_boundary');
  assert.equal(result.confirmedFireCoverageVerified,false);
  assert.equal(result.validNonFireLabelsAvailable,false);
});

test('On-demand weather and perimeters never masquerade as monitored snapshot sources',()=>{
  const result=audit(snap());
  for(const key of ['nws_grid','nifc_perimeter']) {
    assert.equal(row(result,key).status,'not_a_snapshot_source');
    assert.equal(row(result,key).observedInCircle,null);
    assert.equal(row(result,key).capabilityOnly,true);
  }
});

test('Zero observed records are reported counts, NOT fire absence',()=>{
  const result=audit(snap({events:[],incidents:[]}));
  assert.equal(row(result,'VIIRS_NOAA20_NRT').observedInCircle,0);
  assert.equal(row(result,'nifc_wfigs').observedInCircle,0);
  assert.equal(result.regionCoverageVerified,false);
  assert.ok(result.notes.some(s=>s.includes('never establish wildfire absence')));
});

test('Unavailable snapshot never presents zero observations or success',()=>{
  const result=audit(snap({manifest:{last_scan_at:null,data_status:'unknown'}}));
  assert.equal(result.snapshotState,'unavailable');
  assert.equal(row(result,'VIIRS_NOAA20_NRT').observedInCircle,null);
  assert.equal(row(result,'VIIRS_NOAA20_NRT').status,'snapshot_unavailable');
});

test('Old, partial and truncated scans do not claim complete coverage',()=>{
  const stale=audit(snap({manifest:{last_scan_at:new Date(now.getTime()-4*3_600_000).toISOString(),data_status:'fresh'}}));
  assert.equal(stale.snapshotState,'stale');
  assert.equal(row(stale,'nifc_wfigs').status,'stale_snapshot');
  const partial=audit(snap({manifest:{last_scan_at:scan,data_status:'partial',truncated:true}}));
  assert.equal(partial.snapshotState,'partial');
  assert.equal(row(partial,'nifc_wfigs').status,'snapshot_partial');
  const bad=audit(snap({sources:[{key:'VIIRS_NOAA20_NRT',status:'failed',consecutive_failures:3}]}));
  assert.equal(row(bad,'VIIRS_NOAA20_NRT').status,'failed');
  assert.equal(row(bad,'VIIRS_NOAA20_NRT').consecutiveFailures,3);
  assert.equal(row(bad,'cwfis').status,'unreported');
});

test('Future observation and late receipt excluded at decision time',()=>{
  const futureObs=candidate('future',179.9,'VIIRS_NOAA20_NRT',
    new Date(now.getTime()+3_600_000).toISOString());
  const futureReceipt={...candidate('late'),received_at:
    new Date(now.getTime()+3_600_000).toISOString()};
  const futureAgency={...incident('cwfis','future'),modified_at:
    new Date(now.getTime()+3_600_000).toISOString()};
  const result=audit(snap({events:[futureObs,futureReceipt],incidents:[futureAgency]}));
  assert.equal(row(result,'VIIRS_NOAA20_NRT').observedInCircle,0);
  assert.equal(row(result,'cwfis').observedInCircle,0);
});

test('Outside-region or out-of-window events excluded but current agency layer retained',()=>{
  const old=new Date(now.getTime()-9*3_600_000).toISOString();
  const result=audit(snap({events:[candidate('old',179.9,'VIIRS_NOAA20_NRT',old),
    candidate('outside',170)],incidents:[incident('cwfis','near'),incident('cwfis','far',150)]}),
    circle,6);
  assert.equal(row(result,'VIIRS_NOAA20_NRT').observedInCircle,0);
  assert.equal(row(result,'cwfis').observedInCircle,1);
});

test('Repeated cells from same source count once by recorded event ID',()=>{
  const one=candidate('same');
  const result=audit(snap({events:[one,{...one},candidate('different')],incidents:[]}));
  assert.equal(row(result,'VIIRS_NOAA20_NRT').observedInCircle,2);
});

test('Unknown selected regions rejected and output serialized without undefined inference',()=>{
  assert.throws(()=>audit(snap(),{...circle,radiusKm:300}),RangeError);
  assert.throws(()=>audit(snap(),circle,12),RangeError);
  const result=audit(snap());
  assert.equal(JSON.parse(JSON.stringify(result)).rows.length,6);
  assert.equal(typeof result.createdAt,'string');
  assert.equal(result.snapshotTruncated,false);
});
