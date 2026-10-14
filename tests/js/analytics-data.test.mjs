import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validatePilot, selectPilot, validateEnvironment, selectEnvironment,
  validateCatalog, validatePairedCatalog, validateAnnualArchive,
  selectAnnualArchive, annualYearSummary, validateSpatialRecurrence,
  selectSpatialRecurrence, validateStandardReadiness} from '../../public/analytics-data.mjs';

test('standard VIIRS catalog pairs remain neither exposure nor fire outcomes', () => {
  const evidence = validateStandardReadiness(JSON.parse(readFileSync(new URL(
    '../../public/data/antalya-standard-granule-readiness-2025-01-06-07.json', import.meta.url))));
  assert.equal(evidence.population.paired_intervals,6);
  assert.equal(evidence.daily_rows[0].archived_noaa20_pixels,1);
  assert.equal(evidence.daily_rows[1].observation_state,'no_archived_record_unverified_opportunity');
  assert.equal(evidence.no_detection_count,null);
  assert.throws(() => validateStandardReadiness({...evidence, cell_exposure_verified:true}));
  assert.throws(() => validateStandardReadiness({...evidence, no_detection_count:0}));
});

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

const weather = validateEnvironment(JSON.parse(readFileSync(new URL('../../public/data/batman-weather-context-2026-10-11.json', import.meta.url))));
const sacramento = validateEnvironment(JSON.parse(readFileSync(new URL('../../public/data/sacramento-weather-context-2026-10-11.json', import.meta.url))));

test('real station pilot preserves join denominators and unknown exposure', () => {
  assert.equal(weather.population.raw_pixels,125);
  assert.equal(weather.population.candidate_cell_hours,56);
  assert.equal(weather.population.candidate_hours,6);
  assert.equal(weather.population.matched_candidate_hours_temperature_c,4);
  assert.equal(selectEnvironment(weather,'temperature_c').length,weather.weather_hourly.length);
  assert.ok(weather.candidate_hours.every(row => row.weather_observed_at === null ||
    row.weather_observed_at <= row.observed_hour));
  assert.throws(() => validateEnvironment({...weather, observation_opportunity_verified:true}));
  assert.throws(() => selectEnvironment(weather,'precipitation'));
});

test('second real station keeps regions and missing hours distinct', () => {
  assert.equal(sacramento.region.region_id, 'SACRAMENTO_25KM');
  assert.equal(sacramento.population.raw_pixels, 22);
  assert.equal(sacramento.population.candidate_hours, 6);
  assert.equal(sacramento.population.matched_candidate_hours_temperature_c, 5);
  assert.equal(sacramento.population.weather_rows_in_range, 51);
  assert.equal(sacramento.candidate_hours.filter(row => row.temperature_c === null).length, 1);
  assert.notEqual(sacramento.pixel_study_id, weather.pixel_study_id);
  assert.ok(sacramento.candidate_hours.every(row => row.satellite_observation_opportunity === 'unknown'));
});

test('real CMR catalog context keeps unverified exposure and source denominators', () => {
  const catalog = validateCatalog(JSON.parse(readFileSync(new URL(
    '../../public/data/batman-cmr-context-2026-10-11.json', import.meta.url))));
  assert.equal(catalog.population.catalog_granules, catalog.granules.length);
  assert.equal(catalog.population.candidate_provider_minutes, catalog.candidate_provider_minutes.length);
  assert.equal(catalog.population.archived_raw_pixels,
    catalog.candidate_provider_minutes.reduce((n, row) => n + row.raw_pixels, 0));
  assert.equal(catalog.observation_opportunity_verified, false);
  assert.equal(catalog.no_detection_count, null);
  assert.throws(() => validateCatalog({...catalog, observation_opportunity_verified:true}));
  assert.throws(() => validateCatalog({...catalog, no_detection_count:0}));
});

test('real paired L1/L2 catalog remains metadata only', () => {
  const geo = validateCatalog(JSON.parse(readFileSync(new URL(
    '../../public/data/batman-cmr-context-2026-10-11.json', import.meta.url))));
  const paired = validatePairedCatalog(JSON.parse(readFileSync(new URL(
    '../../public/data/batman-cmr-paired-products-2026-10-11.json', import.meta.url))), geo);
  assert.equal(paired.population.geolocation_granules,20);
  assert.equal(paired.population.active_fire_granules,20);
  assert.equal(paired.population.paired_intervals,20);
  assert.equal(paired.population.candidate_minutes_with_both_catalogs,5);
  assert.equal(paired.population.candidate_provider_minutes,7);
  assert.equal(paired.observation_opportunity_verified,false);
  assert.equal(paired.no_detection_count,null);
  assert.throws(() => validatePairedCatalog({...paired, observation_opportunity_verified:true}, geo));
  assert.throws(() => validatePairedCatalog({...paired, no_detection_count:0}, geo));
  assert.throws(() => validatePairedCatalog({...paired, geolocation_report_sha256:'0'.repeat(64)}, geo));
});

test('three-year real country archive keeps sensor, weather and exposure grain separate', () => {
  const annual = validateAnnualArchive(JSON.parse(readFileSync(new URL(
    '../../public/data/antalya-annual-context-2023-2025.json', import.meta.url))));
  assert.equal(annual.population.source_files,6);
  assert.equal(annual.population.weather_files,3);
  assert.equal(annual.population.country_source_rows,257907);
  assert.equal(annual.population.selected_raw_pixels,1340);
  assert.equal(annual.population.candidate_provider_hours,994);
  assert.equal(annual.population.weather_matched_provider_hours_temperature_c,988);
  assert.equal(annual.observation_opportunity_verified,false);
  assert.equal(annual.no_detection_count,null);
  const {months} = selectAnnualArchive(annual, {from:'2025-01',to:'2025-12',
    provider:'all',variable:'temperature_c'});
  assert.equal(months.length,12);
  assert.equal(months.reduce((n,row) => n+row.rawPixels,0),212);
  assert.ok(months.every(row => row.observationOpportunity === 'unknown'));
  assert.throws(() => selectAnnualArchive(annual,{from:'2025-12',to:'2025-01',
    provider:'all',variable:'temperature_c'}));
  assert.throws(() => validateAnnualArchive({...annual, observation_opportunity_verified:true}));
  assert.throws(() => validateAnnualArchive({...annual, no_detection_count:0}));
});

test('independently chosen Dalaman study retains sparse yearly denominators', () => {
  const dalaman = validateAnnualArchive(JSON.parse(readFileSync(new URL(
    '../../public/data/dalaman-annual-context-2023-2025.json', import.meta.url))));
  assert.equal(dalaman.population.country_source_rows,257907);
  assert.equal(dalaman.population.selected_raw_pixels,79);
  assert.equal(dalaman.population.candidate_provider_hours,38);
  assert.equal(dalaman.population.weather_matched_provider_hours_temperature_c,38);
  assert.deepEqual(annualYearSummary(dalaman).map(row => [row.year,row.rawPixels,row.daysWithArchivedCandidates]),
    [['2023',8,8],['2024',18,10],['2025',53,9]]);
  assert.equal(annualYearSummary(dalaman)[2].candidateCellHours,18);
  assert.equal(annualYearSummary(dalaman)[2].positiveSensorHours,15);
  assert.equal(dalaman.observation_opportunity_verified,false);
  assert.equal(dalaman.no_detection_count,null);
});

test('real spatial recurrence keeps source heuristic below independent classification', () => {
  const spatial = validateSpatialRecurrence(JSON.parse(readFileSync(new URL(
    '../../public/data/turkey-spatial-recurrence-2023-2025.json', import.meta.url))));
  assert.equal(spatial.population.selected_raw_pixels,1419);
  assert.equal(spatial.observation_opportunity_verified,false);
  const antalya = selectSpatialRecurrence(spatial,'ANTALYA_25KM');
  const dalaman = selectSpatialRecurrence(spatial,'DALAMAN_25KM');
  assert.equal(antalya.selected_raw_pixels,1340);
  assert.equal(dalaman.selected_raw_pixels,79);
  assert.equal(antalya.published_bins[0].raw_pixels,748);
  assert.equal(antalya.published_bins[0].classification,'potential_static_thermal_source');
  assert.equal(antalya.published_bins[0].source_type_counts['2'],741);
  assert.equal(antalya.published_bins[0].independently_classified,false);
  assert.throws(() => validateSpatialRecurrence({...spatial, independent_fire_outcome_valid:true}));
  assert.throws(() => selectSpatialRecurrence(spatial,'not-a-region'));
});
