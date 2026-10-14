import {validatePilot, selectPilot, validateEnvironment, selectEnvironment,
  environmentalVariables, validateCatalog} from './analytics-data.mjs';

const el = id => document.getElementById(id);
const cell = (row, value) => {
  const td = document.createElement('td'); td.textContent = value; row.append(td);
};
const number = value => value === null ? '—' : Number(value).toLocaleString();
const method = (label, value) => {
  const dt = document.createElement('dt'); dt.textContent = label;
  const dd = document.createElement('dd'); dd.textContent = value;
  el('analytics-methods').append(dt, dd);
};

function draw(report) {
  const regionId = el('analytics-region').value;
  const from = el('analytics-from').value;
  const to = el('analytics-to').value;
  const {daily, comparison} = selectPilot(report, {regionId, from, to});
  const region = report.regions.find(item => item.region_id === regionId);
  el('analytics-selection-note').textContent = `${regionId}: ${region.radius_km} km circle at ${region.latitude}°, ${region.longitude}°. ${daily.length} UTC days contain archived candidates in the selected range; unlisted days have unknown observation opportunity.`;
  el('analytics-days').replaceChildren();
  el('analytics-chart').replaceChildren();
  const maximum = Math.max(1, ...daily.map(row => row.new_candidate_cell_hours));
  for (const day of daily) {
    const tr = document.createElement('tr');
    cell(tr, day.observed_date); cell(tr, number(day.new_candidate_cell_hours));
    cell(tr, number(day.new_raw_pixels));
    cell(tr, day.rolling_3_observed_days === null ? '—' : number(day.rolling_3_observed_days));
    cell(tr, 'Partial archive'); el('analytics-days').append(tr);
    const bar = document.createElement('div'); bar.className = 'analytics-bar';
    const count = document.createElement('strong'); count.textContent = number(day.new_candidate_cell_hours);
    const column = document.createElement('span');
    column.style.height = `${Math.max(2, Math.round(115 * day.new_candidate_cell_hours / maximum))}px`;
    const date = document.createElement('small'); date.textContent = day.observed_date.slice(5);
    bar.append(count, column, date); el('analytics-chart').append(bar);
  }
  if (!daily.length) {
    const note = document.createElement('p');
    note.textContent = 'No archived candidate days in this selection. Observation opportunity is unverified.';
    el('analytics-chart').append(note);
  }
  el('analytics-chart').setAttribute('aria-label', `Daily candidate cell-hours in ${regionId}, ${from} to ${to}; all periods have incomplete observation coverage`);
  el('analytics-comparison').replaceChildren();
  for (const row of comparison) {
    const tr = document.createElement('tr');
    cell(tr, row.regionId); cell(tr, number(row.candidateCellHours));
    cell(tr, number(row.rawPixels)); el('analytics-comparison').append(tr);
  }
}

function drawEnvironment(report) {
  const variable = el('weather-variable').value;
  const points = selectEnvironment(report, variable);
  const maximum = Math.max(1, ...points.map(point => point.value ?? 0));
  el('weather-chart').replaceChildren();
  for (const [index, point] of points.entries()) {
    const bar = document.createElement('div');
    bar.className = `analytics-bar${point.candidateCellHours === null ? '' : ' has-candidate'}`;
    bar.title = `${point.hour}: ${point.value ?? 'missing'} ${environmentalVariables[variable]}; ${point.candidateCellHours === null ? 'satellite opportunity unknown' : `${point.candidateCellHours} archived candidate cell-hours`}`;
    const column = document.createElement('span');
    column.style.height = `${point.value === null ? 2 : Math.max(2, Math.round(100 * point.value / maximum))}px`;
    const tick = document.createElement('small');
    tick.textContent = index % 6 === 0 ? point.hour.slice(5, 13) : '';
    bar.append(column, tick); el('weather-chart').append(bar);
  }
  el('weather-chart').setAttribute('aria-label', `${environmentalVariables[variable]} at ${report.station.name}, ${report.start_date} to ${report.end_date}; amber marks archived candidate hours; other hours have unknown satellite coverage`);
  const stats = report.descriptive_statistics[variable];
  el('weather-summary').textContent = `${stats.station_observation_n} source station values; mean ${stats.station_mean ?? 'unavailable'}; ${stats.matched_candidate_hour_n}/${report.population.candidate_hours} candidate hours matched for this variable. Values at matched candidate hours are exploratory context, not independent pixel samples or evidence of a weather effect.`;
}

async function startEnvironment() {
  try {
    const response = await fetch('./data/batman-weather-context-2026-10-11.json', {cache:'no-store'});
    if (!response.ok) throw new Error(`Report unavailable (${response.status})`);
    const report = validateEnvironment(await response.json());
    el('weather-candidates').replaceChildren();
    for (const item of report.candidate_hours) {
      const tr = document.createElement('tr');
      for (const value of [item.observed_hour, item.candidate_cell_hours, item.raw_pixels,
        item.weather_observed_at ?? 'Unavailable', item.temperature_c === null ? '—' : `${item.temperature_c} °C`,
        item.wind_speed_m_s === null ? '—' : `${item.wind_speed_m_s} m/s`,
        item.relative_humidity_pct === null ? '—' : `${item.relative_humidity_pct} %`]) cell(tr, value);
      el('weather-candidates').append(tr);
    }
    el('weather-provenance').textContent = `NOAA GHCNh ${report.station.id}, ${report.weather_documentation_version}, ${report.weather_license}; ${report.population.weather_rows_in_range} station rows from ${number(report.population.source_rows)} annual file rows; ${report.population.raw_pixels} FIRMS raw pixels in ${report.population.candidate_cell_hours} distinct candidate cell-hours. Source SHA-256: ${report.source_sha256}. Source file last modified ${report.weather_source_last_modified}; each observation's first availability is unknown. The station file can be revised. No satellite acquisition mask or independent fire outcome is present.`;
    el('weather-variable').addEventListener('change', () => drawEnvironment(report));
    drawEnvironment(report);
    el('weather-status').textContent = 'Retrospective station pilot loaded.';
  } catch (error) {
    el('weather-status').textContent = `Historical weather context unavailable: ${error.message}`;
    el('weather-chart').replaceChildren();
  }
}

async function startCatalog() {
  try {
    const response = await fetch('./data/batman-cmr-context-2026-10-11.json', {cache:'no-store'});
    if (!response.ok) throw new Error(`Report unavailable (${response.status})`);
    const report = validateCatalog(await response.json());
    el('catalog-candidates').replaceChildren();
    for (const item of report.candidate_provider_minutes) {
      const tr = document.createElement('tr');
      cell(tr, item.observed_minute.replace('T',' ') + ' UTC');
      cell(tr, item.provider.replace('VIIRS_','').replace('_NRT',''));
      cell(tr, number(item.raw_pixels));
      cell(tr, item.catalog_granule_ids.length
        ? `${item.catalog_granule_ids.length} granule interval${item.catalog_granule_ids.length === 1 ? '' : 's'}`
        : 'No exact interval match; acquisition status unknown');
      el('catalog-candidates').append(tr);
    }
    const count = report.population;
    el('catalog-summary').textContent = `${count.catalog_granules} granules intersect the ${report.query_bbox_wgs84} WGS84 search box; ${count.temporally_matched_candidate_provider_minutes}/${count.candidate_provider_minutes} archived provider-minute groups have an exact catalog interval match. This is not cell-level observation opportunity, and unmatched minutes are not failed observations.`;
    el('catalog-provenance').textContent = `NASA CMR ${report.source_queries.map(query => `${query.product} v${query.collection_version}: ${query.cmr_hits} records, response SHA-256 ${query.response_sha256}`).join(' · ')}. Queried ${report.catalog_fetched_at}; granule files were not downloaded. Source revisions and acquisition-minute conventions can change this comparison. No negative detection count is calculated.`;
    el('catalog-status').textContent = 'CMR catalog context loaded.';
  } catch (error) {
    el('catalog-status').textContent = `CMR catalog context unavailable: ${error.message}`;
    el('catalog-candidates').replaceChildren();
  }
}

async function start() {
  try {
    const response = await fetch('./data/thermal-capture-pilot-2026-10-13.json', {cache:'no-store'});
    if (!response.ok) throw new Error(`Report unavailable (${response.status})`);
    const report = validatePilot(await response.json());
    const dates = report.daily_rows.map(row => row.observed_date).sort();
    if (!dates.length) throw new Error('No archived observation days');
    for (const region of report.regions) {
      const option = document.createElement('option'); option.value = region.region_id;
      option.textContent = region.region_id.replaceAll('_', ' ');
      el('analytics-region').append(option);
    }
    el('analytics-region').value = 'ANTALYA';
    if (!report.regions.some(region => region.region_id === 'ANTALYA'))
      el('analytics-region').selectedIndex = 0;
    for (const id of ['analytics-from','analytics-to']) {
      el(id).min = dates[0]; el(id).max = dates.at(-1);
    }
    el('analytics-from').value = dates[0]; el('analytics-to').value = dates.at(-1);
    for (const id of ['analytics-region','analytics-from','analytics-to'])
      el(id).addEventListener('change', () => {
        try { draw(report); el('analytics-status').textContent = 'Archived pilot loaded.'; }
        catch (error) {
          el('analytics-status').textContent = error.message;
          for (const result of ['analytics-chart','analytics-days','analytics-comparison'])
            el(result).replaceChildren();
          el('analytics-selection-note').textContent = 'Correct the UTC date range to view evidence.';
        }
      });
    method('Data source', 'NASA FIRMS VIIRS NOAA-20 and NOAA-21 NRT, originally captured public research releases');
    method('Pilot archive', `${report.input_population.verified_scan_receipts} scan receipts; ${number(report.input_population.unique_raw_pixels)} unique raw pixels; ${number(report.input_population.selected_region_raw_pixels)} inside ${report.regions.length} selected circles`);
    method('Source assets', `${report.source_asset_manifest.length} original pixel files with archived SHA-256 and parsed row counts in the downloadable JSON`);
    method('Time span', `${dates[0]} to ${dates.at(-1)} (observed UTC dates; partial archive)`);
    const sourceStates = [...new Set(report.source_receipts.flatMap(scan => Object.keys(scan.source_states)))].sort()
      .map(source => `${source}: ${report.source_receipts.filter(scan => scan.source_states[source] === 'complete').length}/${report.source_receipts.length} complete collector requests`);
    method('Source requests', sourceStates.join(' · ') + '; satellite acquisition coverage unverified');
    method('Archive scan span', `${report.source_receipts[0].scan_at} to ${report.source_receipts.at(-1).scan_at}`);
    method('Evidence SHA-256', report.evidence_sha256);
    method('Model research', report.model_research.status === 'experimental'
      ? `Experimental next-scan collection count only; scientific model comparison ${report.model_research.eligibility?.scientific_model_comparison?.status ?? 'unassessed'}${report.model_research.degenerate_training_target ? '; training target has no variation' : ''}. No validated wildfire prediction.`
      : 'Withheld: ' + report.model_research.reason);
    el('analytics-limits').textContent = report.coverage_warning +
      ' Seasonal/year comparisons, environmental associations and fire validation are unavailable from this short archive.';
    el('analytics-status').textContent = 'Archived pilot loaded.';
    draw(report);
  } catch (error) {
    el('analytics-status').textContent = `Historical analytics unavailable: ${error.message}`;
  }
}

start();
startEnvironment();
startCatalog();
