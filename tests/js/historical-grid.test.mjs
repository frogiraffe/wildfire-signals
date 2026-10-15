import test from 'node:test';import assert from 'node:assert/strict';import {spatialGridCells} from '../../public/historical-grid.mjs';
test('WGS84 boxes remain source geometry not generated fire circles',()=>{
  const boxes=spatialGridCells({published_bins:[{bin_id:'x',bounds_wgs84:[36.9,30.6,36.91,30.61],raw_pixels:8,distinct_dates:3,classification:'recurrently_observed_candidate'}]});
  assert.equal(boxes.length,1);assert.equal(boxes[0].west,30.6);assert.equal(boxes[0].south,36.9);
});
test('reject invalid and reversed geometry',()=>{
  assert.throws(()=>spatialGridCells({published_bins:[{bounds_wgs84:[37,31,36,32],raw_pixels:1}]}),/Invalid grid/);
  assert.throws(()=>spatialGridCells({published_bins:[{bounds_wgs84:[36,31,37,32],raw_pixels:-1}]}),/Invalid grid/);
});
