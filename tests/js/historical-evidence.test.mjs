import test from 'node:test';
import assert from 'node:assert/strict';
import {compareHistoricalEvidence,historicalEvidenceCsv} from '../../public/historical-evidence.mjs';

const sha='a'.repeat(64);
const study=(id,label,n)=>({pilot:{id,label},report:{
  start_date:'2023-01-01',end_date:'2025-12-31',
  source_asset_manifest:[{provider:'VIIRS_NOAA20_STANDARD'}],
  monthly_rows:[{observed_month:'2023-01',provider:'VIIRS_NOAA20_STANDARD',
    raw_pixels:n,candidate_cell_hours:n+1}],
  weather_monthly_rows:[{observed_month:'2023-01',temperature_c_median:20,temperature_c_n:1}],
  evidence_sha256:sha
}});
const selection={from:'2023-01',to:'2023-01',provider:'all',variable:'temperature_c'};
test('historical comparison preserves receipts and never fabricates risk',()=>{
  const report=compareHistoricalEvidence([study('A','Antalya',2),study('D','Dalaman',3)],selection);
  assert.equal(report.rows.length,2);
  assert.equal(report.rows[0].candidateCellHours,3);
  assert.equal(report.rows[1].rawPixels,3);
  assert.equal(report.wildfireRiskComparisonAvailable,false);
  assert.equal(report.fireProbability,null);
  assert.equal(report.rows[0].evidenceSha256,sha);
});
test('CSV escapes untrusted labels and starts with a UTF-8 BOM',()=>{
  const r=compareHistoricalEvidence([study('A','Sample, "quoted"',2)],selection);
  const csv=historicalEvidenceCsv(r);
  assert.ok(csv.startsWith('\uFEFF'));
  assert.ok(csv.includes('"Sample, ""quoted"""'));
});
test('selection outside archived window is rejected',()=>{
  assert.throws(()=>compareHistoricalEvidence([study('A','Antalya',2)],
    {...selection,from:'2022-01'}),/Invalid annual selection/);
});
