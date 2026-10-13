import test from 'node:test';
import assert from 'node:assert/strict';
import {analyzeRegionalSignals} from '../../public/analysis-engine.mjs';

const now=new Date('2026-10-13T12:00:00Z');
const region={latitude:0,longitude:179.95,radiusKm:75};
const H=3_600_000;
const rows=(hoursAgo,source='VIIRS_NOAA20_NRT',lon=179.95,lat=0,other={})=>({
  kind:'satellite_candidate',event_id:`cell-${hoursAgo}-${source}`,
  latitude:lat,longitude:lon,
  observed_at:new Date(now.getTime()-hoursAgo*H).toISOString(),
  sources:[source],...other
});
const snapshot=(events,opts={})=>({
  manifest:{schema_version:1,last_scan_at:now.toISOString(),data_status:'fresh',truncated:false,...opts.manifest},
  events,sources:opts.sources||[
    {key:'VIIRS_NOAA20_NRT',status:'complete'},
    {key:'VIIRS_NOAA21_NRT',status:'complete'}]
});

test('deduplicate cell-hour, calculate temporal counts, sensor and same-cell co-membership',()=>{
  const events=[
    rows(23),rows(18),rows(15),rows(13),rows(11),rows(10),
    rows(3),rows(2),rows(1),rows(1,'VIIRS_NOAA21_NRT'),
    rows(1,'VIIRS_NOAA20_NRT',179.95,0,{event_id:'repeat-again'}),
    rows(2,'VIIRS_NOAA21_NRT')
  ];
  const result=analyzeRegionalSignals(snapshot(events),region,{now,hours:24});
  assert.equal(result.status,'current');
  assert.equal(result.metrics.cellHours,9);
  assert.equal(result.metrics.distinctCells,1);
  assert.equal(result.metrics.recurrentCells,1);
  assert.equal(result.metrics.recurrentCellHours,9);
  assert.equal(result.metrics.consecutiveHourTransitions,4); // 1/2/3 and 10/11, 14/15? see below
  assert.equal(result.metrics.multiSensorCellHours,2);
  assert.equal(result.metrics.multiSensorPercent,22.2);
  assert.deepEqual(result.bins.map(b=>b.cellHours),[1,2,3,0,1,2]);
  assert.equal(result.sensorSeries[0].cellHours,9);
  assert.equal(result.sensorSeries[1].cellHours,2);
  assert.equal(result.sensorCoMembership[0].independentWildfireConfirmation,false);
  assert.equal(result.satelliteOverpassDenominatorAvailable,false);
  assert.equal(result.verifiedWildfireCount,null);
  assert.equal(result.wildfireProbability,null);
  assert.equal(result.hypothesisPValue,null);
  assert.equal(result.sourceCoverage.confirmedFireCoverageVerified,false);
});
test('date-line geometry includes nearby negative longitude and excludes far cells',()=>{
  const data=snapshot([rows(2,'VIIRS_NOAA20_NRT',-179.9),
    rows(2,'VIIRS_NOAA20_NRT',0),
    rows(3,'VIIRS_NOAA21_NRT',-179.9)]);
  const value=analyzeRegionalSignals(data,region,{now,hours:6});
  assert.equal(value.metrics.cellHours,2);
  assert.equal(value.metrics.distinctCells,1);
  assert.equal(value.metrics.recurrentCells,1);
  assert.deepEqual(value.bins.map(b=>b.cellHours),[0,0,1,0,1,0]);
});
test('source filter is explicit: no agency-only fake zero, source metrics are consistent',()=>{
  const data=snapshot([rows(2),rows(2,'VIIRS_NOAA21_NRT'),
                       rows(1,'VIIRS_NOAA21_NRT')]);
  const only=analyzeRegionalSignals(data,region,{now,hours:6,source:'VIIRS_NOAA20_NRT'});
  assert.equal(only.metrics.cellHours,1);
  assert.equal(only.metrics.multiSensorCellHours,0);
  assert.equal(only.sensorSeries.length,1);
  assert.deepEqual(only.selectedSensors,['VIIRS_NOAA20_NRT']);
  assert.throws(()=>analyzeRegionalSignals(data,region,{now,source:'nifc_wfigs'}),RangeError);
});
test('snapshot and received-at future gate rejects look-ahead while preserving earlier records',()=>{
  const data=snapshot([rows(1),rows(3),rows(2,'VIIRS_NOAA21_NRT',179.95,0,{
    received_at:new Date(now.getTime()-30*60_000).toISOString()
  })],{manifest:{last_scan_at:new Date(now.getTime()-2*H).toISOString()}});
  const value=analyzeRegionalSignals(data,region,{now,hours:6});
  assert.equal(value.metrics.cellHours,1);
  assert.equal(value.metrics.lastObservedAt,rows(3).observed_at);
  assert.equal(value.status,'stale');
  assert.equal(value.metrics.laterMinusEarlier,1);
  assert.equal(value.coverageVerified,false);
});
test('current full snapshot with no candidate is neither zero probability nor verified absence',()=>{
  const report=analyzeRegionalSignals(snapshot([]),region,{now});
  assert.equal(report.metrics.cellHours,0);
  assert.equal(report.metrics.distinctCells,0);
  assert.equal(report.metrics.multiSensorPercent,null);
  assert.equal(report.metrics.laterToEarlierRatio,null);
  assert.equal(report.metrics.theilSenCellHoursPerHour,0);
  assert.equal(report.metrics.trendDirection,'flat_descriptive');
  assert.equal(report.verifiedNonfireCount,null);
  assert.equal(report.wildfireProbability,null);
  assert.equal(report.metrics.lastObservedAt,null);
});
test('unavailable snapshot does not expose fabricated zeros, and stale/partial/truncated are explicit',()=>{
  const data=snapshot([rows(2)]);
  const missing=analyzeRegionalSignals({...data,manifest:{last_scan_at:null}},region,{now});
  assert.equal(missing.analysisAvailable,false);
  assert.equal(missing.status,'unavailable');
  assert.equal(missing.metrics.cellHours,null);
  assert.ok(missing.bins.every(b=>b.cellHours===null));
  const failed=analyzeRegionalSignals(snapshot([rows(2)],{
    sources:[{key:'VIIRS_NOAA20_NRT',status:'failed'},
             {key:'VIIRS_NOAA21_NRT',status:'complete'}]}),region,{now});
  assert.equal(failed.status,'incomplete');
  assert.deepEqual(failed.sourceStates.map(x=>x.status),['failed','complete']);
  assert.equal(failed.metrics.cellHours,1);
  assert.ok(failed.limitations.some(x=>x.includes('Incomplete source')));
  const cut=analyzeRegionalSignals(snapshot([rows(2)],{
    manifest:{truncated:true}}),region,{now});
  assert.equal(cut.status,'incomplete');
  assert.equal(cut.sourceCoverage.snapshotTruncated,true);
});
test('theil-sen descriptive slope and bin median/MAD reflect supplied observations only',()=>{
  const events=[rows(4.5),rows(3.5),rows(3.4, 'VIIRS_NOAA20_NRT',179.91),
                rows(2.5),rows(2.4,'VIIRS_NOAA20_NRT',179.91),rows(2.3,'VIIRS_NOAA20_NRT',179.96),
                rows(1.5),rows(1.4,'VIIRS_NOAA20_NRT',179.91),rows(1.3,'VIIRS_NOAA20_NRT',179.96),
                rows(1.2,'VIIRS_NOAA20_NRT',-179.99)];
  const result=analyzeRegionalSignals(snapshot(events),region,{now,hours:6});
  assert.deepEqual(result.bins.map(x=>x.cellHours),[0,1,2,3,4,0]);
  assert.equal(result.metrics.medianBinCellHours,1.5);
  assert.equal(result.metrics.madBinCellHours,1.5);
  assert.equal(result.metrics.laterMinusEarlier,4);
  assert.equal(result.metrics.laterToEarlierRatio,3.5);
  assert.equal(result.metrics.trendDirection,'upward_descriptive');
  assert.ok(result.metrics.theilSenCellHoursPerHour>0);
  assert.equal(result.hypothesisPValue,null);
});
test('inputs reject invalid coordinates, clocks, windows and weird source filters',()=>{
  const data=snapshot([]);
  for(const r of [{...region,latitude:91},{...region,radiusKm:0}])
    assert.throws(()=>analyzeRegionalSignals(data,r,{now}),RangeError);
  assert.throws(()=>analyzeRegionalSignals(data,region,{hours:12,now}),RangeError);
  assert.throws(()=>analyzeRegionalSignals(data,region,{hours:24,now:new Date('invalid')}),RangeError);
  assert.throws(()=>analyzeRegionalSignals(data,region,{source:'VIIRS_NOT_REAL',now}),RangeError);
});
