import test from 'node:test';
import assert from 'node:assert/strict';
import {formatResearchReport,buildResearchReport} from '../../public/research-report.mjs';
test('published research report visibly preserves independent-outcome limits',()=>{
 const s=formatResearchReport({
  annual:{study:'ANTALYA_25KM',rawPixels:10,candidateCellHours:5,monthsWithArchivedCandidates:2,evidenceSha256:'a'.repeat(64)},
  geography:{publishedBins:3,mappedPixels:7,unpublishedPixels:3,evidenceSha256:'b'.repeat(64)},
  selection:{annual_month_window_utc:{from:'2023-01',to:'2025-12'},sensor:'all'},
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
