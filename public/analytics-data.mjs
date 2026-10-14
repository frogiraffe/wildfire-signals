export function validatePilot(report) {
  if (report?.schema_version !== 1 || !Array.isArray(report.regions) ||
      !Array.isArray(report.daily_rows) || !Array.isArray(report.source_receipts) ||
      !Array.isArray(report.source_asset_manifest) ||
      report.satellite_opportunity_verified !== false || report.verified_fire_count !== null ||
      !/^[a-f0-9]{64}$/.test(report.evidence_sha256 ?? ''))
    throw new Error('Unsupported or incomplete historical evidence report');
  const ids = new Set(report.regions.map(region => region.region_id));
  if (!ids.size || report.daily_rows.some(row => !ids.has(row.region_id) ||
      !/^\d{4}-\d\d-\d\d$/.test(row.observed_date) ||
      !Number.isSafeInteger(row.new_candidate_cell_hours) || row.new_candidate_cell_hours < 0 ||
      row.archive_period_complete !== false))
    throw new Error('Invalid pilot observation rows');
  if (report.source_asset_manifest.some(asset => !/^[a-f0-9]{64}$/.test(asset.asset_sha256 ?? '')))
    throw new Error('Invalid source asset manifest');
  return report;
}

export function selectPilot(report, {regionId, from, to}) {
  if (!report.regions.some(region => region.region_id === regionId) ||
      !/^\d{4}-\d\d-\d\d$/.test(from) || !/^\d{4}-\d\d-\d\d$/.test(to) || from > to)
    throw new Error('Invalid region or UTC date range');
  const inRange = report.daily_rows.filter(row => row.observed_date >= from && row.observed_date <= to);
  const daily = inRange.filter(row => row.region_id === regionId)
    .sort((a, b) => a.observed_date.localeCompare(b.observed_date));
  const comparison = report.regions.map(region => {
    const rows = inRange.filter(row => row.region_id === region.region_id);
    return {regionId: region.region_id, daysWithArchivedCandidates: rows.length,
      candidateCellHours: rows.length ? rows.reduce((n, row) => n + row.new_candidate_cell_hours, 0) : null,
      rawPixels: rows.length ? rows.reduce((n, row) => n + row.new_raw_pixels, 0) : null};
  });
  return {daily, comparison};
}

export const environmentalVariables = {
  temperature_c: 'Air temperature (°C)',
  wind_speed_m_s: 'Wind speed (m/s)',
  relative_humidity_pct: 'Relative humidity (%)'
};

export function validateEnvironment(report) {
  if (report?.schema_version !== 1 || report.status !== 'retrospective_descriptive_exploration' ||
      report.observation_opportunity_verified !== false ||
      report.independent_fire_outcome_valid !== false ||
      report.environment_first_available_at !== null ||
      !/^[a-f0-9]{64}$/.test(report.source_sha256 ?? '') ||
      !/^[a-f0-9]{64}$/.test(report.evidence_sha256 ?? '') ||
      !Array.isArray(report.weather_hourly) || !Array.isArray(report.candidate_hours) ||
      !report.station?.id || !report.region?.region_id)
    throw new Error('Unsupported environmental evidence report');
  if (report.candidate_hours.some(row =>
      row.satellite_observation_opportunity !== 'unknown' ||
      (row.weather_observed_at !== null && row.weather_observed_at > row.observed_hour) ||
      !Number.isSafeInteger(row.candidate_cell_hours) || row.candidate_cell_hours < 0))
    throw new Error('Invalid retrospective observation join');
  return report;
}

export function selectEnvironment(report, variable) {
  if (!(variable in environmentalVariables)) throw new Error('Invalid environmental variable');
  return report.weather_hourly.map(row => ({hour: row.hour, value: row[variable],
    candidateCellHours: row.candidate_cell_hours}));
}

export function validateCatalog(report) {
  if (report?.schema_version !== 1 || report.status !== 'granule_catalog_context_only' ||
      report.observation_opportunity_verified !== false || report.no_detection_count !== null ||
      report.catalog_first_available_at !== null ||
      report.granule_files_downloaded !== false ||
      !/^[a-f0-9]{64}$/.test(report.evidence_sha256 ?? '') ||
      !Array.isArray(report.source_queries) || report.source_queries.length !== 2 ||
      !Array.isArray(report.granules) || !Array.isArray(report.candidate_provider_minutes) ||
      report.population?.catalog_granules !== report.granules.length ||
      report.population?.candidate_provider_minutes !== report.candidate_provider_minutes.length ||
      report.population?.archived_raw_pixels !== report.candidate_provider_minutes.reduce(
        (n, row) => n + row.raw_pixels, 0) ||
      report.population?.temporally_matched_candidate_provider_minutes !==
        report.candidate_provider_minutes.filter(row => row.catalog_granule_ids.length).length ||
      report.source_queries.some(query => !/^[a-f0-9]{64}$/.test(query.response_sha256 ?? '')))
    throw new Error('Unsupported or incomplete CMR catalog context');
  return report;
}

export function validatePairedCatalog(report, geolocation) {
  if (report?.schema_version !== 1 || report.status !== 'paired_product_catalog_context_only' ||
      report.geolocation_report_sha256 !== geolocation.evidence_sha256 ||
      report.region?.region_id !== geolocation.region.region_id ||
      report.study_id !== geolocation.study_id ||
      report.start_date !== geolocation.start_date || report.end_date !== geolocation.end_date ||
      report.query_bbox_wgs84 !== geolocation.query_bbox_wgs84 ||
      report.geolocation_granule_contents_verified !== false ||
      report.active_fire_granule_contents_verified !== false ||
      report.observation_opportunity_verified !== false || report.no_detection_count !== null ||
      report.active_catalog_first_available_at !== null ||
      !/^[a-f0-9]{64}$/.test(report.evidence_sha256 ?? '') ||
      !Array.isArray(report.source_queries) || report.source_queries.length !== 2 ||
      !Array.isArray(report.product_intervals) ||
      !Array.isArray(report.candidate_provider_minutes) ||
      report.population?.geolocation_granules !== geolocation.granules.length ||
      report.population?.candidate_provider_minutes !== geolocation.candidate_provider_minutes.length ||
      report.population?.archived_raw_pixels !== geolocation.population.archived_raw_pixels ||
      report.population?.paired_intervals !== report.product_intervals.filter(
        item => item.pair_status === 'both_catalogued').length ||
      report.population?.candidate_minutes_with_both_catalogs !== report.candidate_provider_minutes.filter(
        item => item.pair_status === 'both_catalogued').length ||
      report.candidate_provider_minutes.some((row, index) =>
        row.observed_minute !== geolocation.candidate_provider_minutes[index]?.observed_minute ||
        row.provider !== geolocation.candidate_provider_minutes[index]?.provider ||
        row.raw_pixels !== geolocation.candidate_provider_minutes[index]?.raw_pixels ||
        !['both_catalogued','geolocation_only','active_fire_only','neither_exact_interval'].includes(row.pair_status)))
    throw new Error('Unsupported or incomplete paired CMR catalog context');
  return report;
}

export const annualVariables = {
  temperature_c: 'Temperature (°C)',
  wind_speed_m_s: 'Wind speed (m/s)',
  relative_humidity_pct: 'Relative humidity (%)'
};

export function validateAnnualArchive(report) {
  const count = (key) => report.population?.[key];
  const pixels = rows => rows.reduce((sum, row) => sum + row.raw_pixels, 0);
  if (report?.schema_version !== 1 || report.status !== 'retrospective_standard_archive_exploration' ||
      report.observation_opportunity_verified !== false || report.no_detection_count !== null ||
      report.independent_fire_outcome_valid !== false || report.statistical_relationship_supported !== false ||
      report.thermal_first_available_at !== null || report.environment_first_available_at !== null ||
      !/^[a-f0-9]{64}$/.test(report.evidence_sha256 ?? '') ||
      !Array.isArray(report.source_asset_manifest) || !Array.isArray(report.weather_asset_manifest) ||
      !Array.isArray(report.daily_rows) || !Array.isArray(report.monthly_rows) ||
      !Array.isArray(report.weather_monthly_rows) || !Array.isArray(report.candidate_provider_hours) ||
      count('source_files') !== report.source_asset_manifest.length ||
      count('weather_files') !== report.weather_asset_manifest.length ||
      count('selected_raw_pixels') !== pixels(report.monthly_rows) ||
      count('selected_raw_pixels') !== pixels(report.daily_rows) ||
      count('candidate_provider_hours') !== report.candidate_provider_hours.length ||
      report.source_asset_manifest.some(item => !/^[a-f0-9]{64}$/.test(item.sha256 ?? '')) ||
      report.weather_asset_manifest.some(item => !/^[a-f0-9]{64}$/.test(item.sha256 ?? '')) ||
      report.monthly_rows.some(item => !/^\d{4}-(0[1-9]|1[0-2])$/.test(item.observed_month) ||
        !Number.isSafeInteger(item.raw_pixels) || item.raw_pixels < 0 ||
        item.satellite_observation_opportunity !== 'unknown') ||
      report.candidate_provider_hours.some(item => item.satellite_observation_opportunity !== 'unknown' ||
        (item.weather_observed_at !== null && item.weather_observed_at > item.first_candidate_minute)))
    throw new Error('Unsupported or inconsistent annual archive');
  return report;
}

export function selectAnnualArchive(report, {from, to, provider, variable}) {
  const month = /^\d{4}-(0[1-9]|1[0-2])$/;
  const providers = new Set(report.source_asset_manifest.map(item => item.provider));
  if (!month.test(from) || !month.test(to) || from > to ||
      from < report.start_date.slice(0,7) || to > report.end_date.slice(0,7) ||
      (provider !== 'all' && !providers.has(provider)) || !(variable in annualVariables))
    throw new Error('Invalid annual selection');
  const weather = new Map(report.weather_monthly_rows.map(row => [row.observed_month, row]));
  const grouped = new Map();
  for (const row of report.monthly_rows) {
    if (row.observed_month < from || row.observed_month > to ||
        (provider !== 'all' && row.provider !== provider)) continue;
    const item = grouped.get(row.observed_month) ?? {month: row.observed_month, rawPixels: 0,
      candidateCellHours: 0, daysWithArchivedCandidates: 0, observationOpportunity: 'unknown'};
    item.rawPixels += row.raw_pixels;
    item.candidateCellHours += row.candidate_cell_hours;
    // These per-sensor counts can overlap on the same day; do not add them.
    item.daysWithArchivedCandidates = null;
    const station = weather.get(row.observed_month);
    item.stationMedian = station?.[`${variable}_median`] ?? null;
    item.stationN = station?.[`${variable}_n`] ?? 0;
    grouped.set(row.observed_month, item);
  }
  return {months: [...grouped.values()].sort((a,b) => a.month.localeCompare(b.month))};
}
