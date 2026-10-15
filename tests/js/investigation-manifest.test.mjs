import test from 'node:test';
import assert from 'node:assert/strict';
import {investigationManifest} from '../../public/investigation-manifest.mjs';
const args={study:'ANTALYA_25KM',sensor:'all',from:'2023-01',to:'2025-12',metric:'raw_pixels',gridFilter:'all'};
test('export makes grid temporal scope explicit and does not claim verified outcomes',()=>{
 const m=investigationManifest(args);
 assert.equal(m.spatial_grid_period_utc.month_filter_applied,false);
 assert.equal(m.uncertainty.independent_fire_outcomes_verified,false);
 assert.equal(m.uncertainty.fire_risk_estimate,null);
 assert.match(m.sources.annual,/antalya-annual-context/);
});
test('reject invalid period and forged sensor',()=>{
 assert.throws(()=>investigationManifest({...args,from:'2025-12',to:'2024-01'}),/Invalid/);
 assert.throws(()=>investigationManifest({...args,sensor:'bogus'}),/Invalid/);
});
