import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validatePilot, selectPilot} from '../../public/analytics-data.mjs';

const report = validatePilot(JSON.parse(readFileSync(new URL('../../public/data/thermal-capture-pilot-2026-10-13.json', import.meta.url))));

test('real aggregate is selectable and conserves selected pixel population', () => {
  assert.equal(report.input_population.unique_raw_pixels,
    report.input_population.selected_region_raw_pixels + report.input_population.outside_selected_regions_raw_pixels);
  assert.equal(report.scan_rows.reduce((sum, row) => sum + row.new_raw_pixels, 0),
    report.input_population.selected_region_raw_pixels);
  const selection = selectPilot(report, {regionId:'ANTALYA', from:'2026-10-09', to:'2026-10-13'});
  assert.ok(selection.daily.length > 0);
  assert.equal(selection.comparison.length, report.regions.length);
  assert.equal(selection.comparison.find(row => row.regionId === 'ANTALYA').candidateCellHours,
    selection.daily.reduce((sum, row) => sum + row.new_candidate_cell_hours, 0));
  assert.ok(selection.daily.every(row => row.archive_period_complete === false));
});

test('absence of archived rows stays unknown, never zero fire activity', () => {
  const selection = selectPilot(report, {regionId:'ALASKA', from:'2026-10-10', to:'2026-10-10'});
  const alaska = selection.comparison.find(row => row.regionId === 'ALASKA');
  if (!selection.daily.length) assert.equal(alaska.candidateCellHours, null);
  assert.throws(() => selectPilot(report, {regionId:'ANTALYA', from:'2026-10-13', to:'2026-10-09'}));
  assert.throws(() => validatePilot({...report, satellite_opportunity_verified:true}));
});
