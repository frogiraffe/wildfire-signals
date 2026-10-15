import test from 'node:test';
import assert from 'node:assert/strict';
import {formatResearchReport,buildResearchReport} from '../../public/research-report.mjs';
test('published research report visibly preserves independent-outcome limits',()=>{
 const s=formatResearchReport({
  annual:{study:'ANTALYA_25KM',rawPixels:10,candidateCellHours:5,monthsWithArchivedCandidates:2,evidenceSha256:'a'.repeat(64)},
  geography:{publishedBins:3,mappedPixels:7,unpublishedPixels:3,evidenceSha256:'b'.repeat(64)},
  selection:{annual_month_window_utc:{from:'2023-01',to:'2025-12'},sensor:'all'},
  provenance:{annualAssets:[],spatialAssets:[]},
  quality:{note:'Detection does not equal fire'}
 });
 assert.match(s,/Satellite opportunity verified: No/);
 assert.match(s,/Independent wildfire outcomes verified: No/);
 assert.match(s,/not restricted to the annual month selection/);
});
test('invalid archive input fails closed',()=>{
 assert.throws(()=>buildResearchReport({}, {},{
 study:'ANTALYA_25KM',sensor:'all',from:'2023-01',to:'2025-12',metric:'raw_pixels',gridFilter:'all'
 }),/Unsupported/);
});

test('report format communicates original source counts',()=>{
 const text=formatResearchReport({annual:{study:'A',rawPixels:2,candidateCellHours:1,monthsWithArchivedCandidates:1,evidenceSha256:'a'.repeat(64)},geography:{publishedBins:1,mappedPixels:2,unpublishedPixels:0,evidenceSha256:'b'.repeat(64)},selection:{annual_month_window_utc:{from:'2023-01',to:'2023-01'},sensor:'all'},provenance:{annualAssets:[{sha256:'c'.repeat(64)}],spatialAssets:[{sha256:'d'.repeat(64)}]},quality:{note:'No fire outcomes'}});
 assert.match(text,/Annual source files: 1/);assert.match(text,/Spatial source files: 1/);
});
