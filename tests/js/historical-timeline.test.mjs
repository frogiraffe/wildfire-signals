import test from 'node:test';
import assert from 'node:assert/strict';
import {historicalTimeline} from '../../public/historical-timeline.mjs';
const report=(id,label,rows)=>({pilot:{id,label},report:{
 start_date:'2023-01-01',end_date:'2025-12-31',evidence_sha256:'a'.repeat(64),
 source_asset_manifest:[{provider:'NOAA20'}],monthly_rows:rows
}});
const month=(observed_month,raw_pixels,candidate_cell_hours)=>({
 observed_month,raw_pixels,candidate_cell_hours,provider:'NOAA20'});
const opts={from:'2023-01',to:'2023-03',provider:'all'};
test('timeline aligns months and keeps absent records as unknown',()=>{
 const a=report('A','Antalya',[month('2023-01',2,1),month('2023-03',3,2)]);
 const d=report('D','Dalaman',[month('2023-02',7,5)]);
 const result=historicalTimeline([a,d],opts);
 assert.deepEqual(result.points.map(x=>x.values),[[2,null],[null,7],[3,null]]);
 assert.equal(result.observationOpportunityVerified,false);
 assert.equal(result.fireRiskInferenceSupported,false);
});
test('sensor and variable selection are applied without misrepresenting missing',()=>{
 const x=report('A','Antalya',[month('2023-01',4,2)]);
 assert.equal(historicalTimeline([x],{...opts,metric:'candidate_cell_hours'}).points[0].values[0],2);
 assert.throws(()=>historicalTimeline([x],{...opts,metric:'risk'}),/Invalid historical timeline/);
 assert.throws(()=>historicalTimeline([x],{...opts,provider:'UNSUPPORTED'}),/Sensor unavailable/);
});
test('bad counts and invalid chronology fail closed',()=>{
 const x=report('A','Antalya',[month('2023-01',-1,2)]);
 assert.throws(()=>historicalTimeline([x],opts),/Malformed historical observation/);
 assert.throws(()=>historicalTimeline([x],{...opts,from:'2022-12'}),/outside archive/);
});
