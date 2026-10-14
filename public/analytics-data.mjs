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
