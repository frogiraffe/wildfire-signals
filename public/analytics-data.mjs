export function validatePilot(report) {
  if (report?.schema_version !== 1 || !Array.isArray(report.regions) ||
      !Array.isArray(report.daily_rows) || !Array.isArray(report.source_receipts) ||
      report.satellite_opportunity_verified !== false || report.verified_fire_count !== null ||
      !/^[a-f0-9]{64}$/.test(report.evidence_sha256 ?? ''))
    throw new Error('Unsupported or incomplete historical evidence report');
  const ids = new Set(report.regions.map(region => region.region_id));
  if (!ids.size || report.daily_rows.some(row => !ids.has(row.region_id) ||
      !/^\d{4}-\d\d-\d\d$/.test(row.observed_date) ||
      !Number.isSafeInteger(row.new_candidate_cell_hours) || row.new_candidate_cell_hours < 0 ||
      row.archive_period_complete !== false))
    throw new Error('Invalid pilot observation rows');
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
