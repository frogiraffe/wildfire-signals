import test from 'node:test';import assert from 'node:assert/strict';
import {historicalAudit} from '../../public/historical-audit.mjs';
const fixture={evidence_sha256:'a'.repeat(64),observation_opportunity_verified:false,independent_fire_outcome_valid:false,regions:[{region:{region_id:'A'},selected_raw_pixels:10,published_bins:[{raw_pixels:3},{raw_pixels:2}]}]};
test('unpublished thermal evidence is not a no-fire label',()=>{
 const audit=historicalAudit(fixture,'A');
 assert.equal(audit.mappedPixels,5);assert.equal(audit.unmappedPixels,5);
 assert.equal(audit.acquiredOpportunity,'unverified');
 assert.equal(audit.validatedWildfireOutcomes,false);
});
test('reject invalid source and inconsistent totals',()=>{
 assert.throws(()=>historicalAudit({...fixture,observation_opportunity_verified:true},'A'),/Unverified/);
 assert.throws(()=>historicalAudit(fixture,'B'),/not represented/);
 assert.throws(()=>historicalAudit({...fixture,regions:[{...fixture.regions[0],selected_raw_pixels:1}]},'A'),/exceeds/);
});
