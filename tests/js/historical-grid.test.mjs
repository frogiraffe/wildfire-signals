import test from 'node:test';import assert from 'node:assert/strict';import {spatialGridCells} from '../../public/historical-grid.mjs';
test('WGS84 boxes remain source geometry not generated fire circles',()=>{
  const boxes=spatialGridCells({published_bins:[{bin_id:'x',bounds_wgs84:[36.9,30.6,36.91,30.61],raw_pixels:8,distinct_dates:3,classification:'recurrently_observed_candidate'}]});
  assert.equal(boxes.length,1);assert.equal(boxes[0].west,30.6);assert.equal(boxes[0].south,36.9);
});
test('reject invalid and reversed geometry',()=>{
  assert.throws(()=>spatialGridCells({published_bins:[{bounds_wgs84:[37,31,36,32],raw_pixels:1}]}),/Invalid grid/);
  assert.throws(()=>spatialGridCells({published_bins:[{bounds_wgs84:[36,31,37,32],raw_pixels:-1}]}),/Invalid grid/);
});

test('sensor counts remain attached to their source cell',()=>{
 const cells=spatialGridCells({published_bins:[{bin_id:'x',bounds_wgs84:[36,30,36.01,30.01],raw_pixels:3,distinct_dates:2,provider_counts:{VIIRS_NOAA20_STANDARD:2,VIIRS_SNPP_STANDARD:1}}]});
 assert.equal(cells[0].providers.VIIRS_NOAA20_STANDARD,2);
 assert.equal(cells[0].providers.VIIRS_SNPP_STANDARD,1);
});
