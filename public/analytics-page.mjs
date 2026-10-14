import {validatePilot, selectPilot, validateEnvironment, selectEnvironment,
  environmentalVariables, validateCatalog, validatePairedCatalog,
  validateAnnualArchive, selectAnnualArchive, annualYearSummary,
  annualVariables} from './analytics-data.mjs';

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

function drawAnnual(report) {
  const variable = el('annual-variable').value;
  const {months} = selectAnnualArchive(report, {from:el('annual-from').value,
    to:el('annual-to').value, provider:el('annual-provider').value, variable});
  const pixelTotal = months.reduce((sum, row) => sum + row.rawPixels, 0);
  el('annual-summary').textContent = `${months.length} selected UTC months; ${number(pixelTotal)} archived candidate pixels. Weather medians use station records from the full month. Neither series has verified satellite exposure; counts are not fire rates. The station was selected around a known thermal archive, so apparent alignment is exploratory.`;
  el('annual-months').replaceChildren();
  for (const [chartId, field, title] of [
    ['annual-thermal-chart','rawPixels','pixels'],
    ['annual-weather-chart','stationMedian',annualVariables[variable]]]) {
    const chart = el(chartId);
    chart.replaceChildren();
    const values = months.map(row => row[field]).filter(value => value !== null);
    const maximum = Math.max(...values, 1);
    const minimum = Math.min(...values, 0);
    const span = Math.max(1, maximum - minimum);
    for (const row of months) {
      const bar = document.createElement('div');
      bar.className = 'analytics-bar';
      const column = document.createElement('span');
      column.style.height = `${row[field] === null ? 2 : Math.max(2, Math.round(110 * (row[field] - minimum) / span))}px`;
      const label = document.createElement('small');
      label.textContent = row.month.slice(2);
      bar.title = `${row.month}: ${row[field] ?? 'unavailable'} ${title}; satellite opportunity unknown`;
      bar.append(column,label); chart.append(bar);
    }
    chart.setAttribute('aria-label', `${title} by UTC month, ${months[0]?.month ?? 'none'} to ${months.at(-1)?.month ?? 'none'}; satellite opportunity unknown`);
  }
  for (const row of months) {
    const tr = document.createElement('tr');
    for (const value of [row.month, number(row.rawPixels), number(row.candidateCellHours),
      row.stationMedian === null ? '—' : `${row.stationMedian} ${annualVariables[variable]}`,
      number(row.stationN), 'Unknown']) cell(tr,value);
    el('annual-months').append(tr);
  }
}

const annualPilots = [
  {id:'ANTALYA_25KM', label:'Antalya', url:'./data/antalya-annual-context-2023-2025.json'},
  {id:'DALAMAN_25KM', label:'Dalaman', url:'./data/dalaman-annual-context-2023-2025.json'}
];

async function startAnnual() {
  const loaded = await Promise.allSettled(annualPilots.map(async pilot => {
    const response = await fetch(pilot.url, {cache:'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const report = validateAnnualArchive(await response.json());
    if (report.region.region_id !== pilot.id) throw new Error('Annual region differs');
    return {pilot,report};
  }));
  const available = loaded.filter(item => item.status === 'fulfilled').map(item => item.value);
  const failures = loaded.length - available.length;
  el('annual-region').replaceChildren();
  el('annual-year-comparison').replaceChildren();
  for (const {pilot, report} of available) {
    const option = document.createElement('option');
    option.value = pilot.id; option.textContent = pilot.label;
    el('annual-region').append(option);
    for (const year of annualYearSummary(report)) {
      const tr = document.createElement('tr');
      for (const value of [`${pilot.label} / ${year.year}`,
        `${number(year.rawPixels)} (${number(year.byProvider.VIIRS_NOAA20_STANDARD)} / ${number(year.byProvider.VIIRS_SNPP_STANDARD)})`,
        number(year.candidateCellHours), number(year.daysWithArchivedCandidates),
        number(year.positiveSensorHours),
        `${number(year.temperatureMatchedPositiveSensorHours)}/${number(year.positiveSensorHours)}`,
        'Unknown']) cell(tr, value);
      el('annual-year-comparison').append(tr);
    }
  }
  if (!available.length) {
    el('annual-status').textContent = 'Annual archive unavailable: neither source report loaded.';
    el('annual-summary').textContent = '';
    return;
  }
  const renderSelected = () => {
    const chosen = available.find(item => item.pilot.id === el('annual-region').value);
    const {report,pilot} = chosen;
    el('annual-provenance').textContent = `${pilot.label}: ${report.population.country_source_rows.toLocaleString()} rows in ${report.population.source_files} NASA annual country files; ${report.population.selected_raw_pixels.toLocaleString()} selected pixels in a ${report.region.radius_km} km circle. ${report.population.station_source_rows.toLocaleString()} rows in ${report.population.weather_files} NOAA station files; ${report.population.weather_matched_provider_hours_temperature_c}/${report.population.candidate_provider_hours} positive sensor-hours have prior station temperature. NASA and NOAA files are revised; original first availability is unknown. Evidence SHA-256: ${report.evidence_sha256}. Source file hashes and revisions are in the download. Weather license: ${report.weather_license}. No independently confirmed wildfire outcome.`;
    el('annual-download').href = pilot.url;
    try {
      drawAnnual(report);
      el('annual-status').textContent = failures ? 'Three-year archive loaded; one study unavailable.' : 'Three-year archive loaded.';
    } catch (error) {
      el('annual-summary').textContent = '';
      el('annual-months').replaceChildren(); el('annual-thermal-chart').replaceChildren();
      el('annual-weather-chart').replaceChildren(); el('annual-status').textContent = error.message;
    }
  };
  for (const id of ['annual-region','annual-from','annual-to','annual-provider','annual-variable'])
    el(id).addEventListener('change', renderSelected);
  renderSelected();
}

const weatherPilots = [
  {id:'BATMAN_25KM', label:'Batman, Türkiye', url:'./data/batman-weather-context-2026-10-11.json'},
  {id:'SACRAMENTO_25KM', label:'Sacramento, California', url:'./data/sacramento-weather-context-2026-10-11.json'}
];

function renderEnvironment(report, url) {
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
    el('weather-download').href = url;
    drawEnvironment(report);
}

async function startEnvironment() {
  const loaded = await Promise.allSettled(weatherPilots.map(async pilot => {
    const response = await fetch(pilot.url, {cache:'no-store'});
    if (!response.ok) throw new Error(`Report unavailable (${response.status})`);
    const report = validateEnvironment(await response.json());
    if (report.region.region_id !== pilot.id) throw new Error('Station report region differs');
    return {pilot, report};
  }));
  const available = loaded.filter(result => result.status === 'fulfilled').map(result => result.value);
  const failures = loaded.length - available.length;
  el('weather-region').replaceChildren();
  el('weather-comparison').replaceChildren();
  for (const {pilot, report} of available) {
    const option = document.createElement('option'); option.value = pilot.id;
    option.textContent = pilot.label; el('weather-region').append(option);
    const tr = document.createElement('tr');
    for (const value of [pilot.label, number(report.population.weather_rows_in_range),
      number(report.population.raw_pixels), number(report.population.candidate_hours),
      `${report.population.matched_candidate_hours_temperature_c}/${report.population.candidate_hours}`,
      'Unknown']) cell(tr, value);
    el('weather-comparison').append(tr);
  }
  if (!available.length) {
    el('weather-status').textContent = 'Historical weather context unavailable: neither source report loaded.';
    el('weather-chart').replaceChildren();
    return;
  }
  const renderSelected = () => {
    const chosen = available.find(item => item.pilot.id === el('weather-region').value);
    renderEnvironment(chosen.report, chosen.pilot.url);
  };
  el('weather-region').addEventListener('change', renderSelected);
  el('weather-variable').addEventListener('change', renderSelected);
  renderSelected();
  el('weather-status').textContent = failures
    ? `Retrospective station pilot loaded; Historical weather context unavailable for ${failures} pilot.`
    : 'Retrospective station pilot loaded.';
}

async function startCatalog() {
  try {
    const response = await fetch('./data/batman-cmr-context-2026-10-11.json', {cache:'no-store'});
    if (!response.ok) throw new Error(`Report unavailable (${response.status})`);
    const report = validateCatalog(await response.json());
    let paired = null;
    try {
      const pairedResponse = await fetch('./data/batman-cmr-paired-products-2026-10-11.json', {cache:'no-store'});
      if (!pairedResponse.ok) throw new Error(`Report unavailable (${pairedResponse.status})`);
      paired = validatePairedCatalog(await pairedResponse.json(), report);
      const pairCounts = paired.population;
      el('pair-summary').textContent = `${pairCounts.paired_intervals} exact same-platform six-minute intervals have both geolocation and active-fire product catalog entries; ${pairCounts.candidate_minutes_with_both_catalogs}/${pairCounts.candidate_provider_minutes} archived provider-minute groups fall inside such intervals. This remains catalog metadata, not verified cell-level observation or no-detection evidence.`;
      el('pair-provenance').textContent = `NASA CMR active-fire L2 ${paired.source_queries.map(query => `${query.product} v${query.collection_version}: ${query.cmr_hits} records, response SHA-256 ${query.response_sha256}`).join(' · ')}. Queried ${paired.active_catalog_fetched_at}; original L1 and L2 files were not inspected. Catalog metadata update times do not establish first availability.`;
      el('pair-status').textContent = 'Active-fire product catalog context loaded.';
    } catch (error) {
      el('pair-status').textContent = `Active-fire product catalog context unavailable: ${error.message}`;
      el('pair-summary').textContent = '';
      el('pair-provenance').textContent = '';
    }
    el('catalog-candidates').replaceChildren();
    for (const [index, item] of report.candidate_provider_minutes.entries()) {
      const tr = document.createElement('tr');
      cell(tr, item.observed_minute.replace('T',' ') + ' UTC');
      cell(tr, item.provider.replace('VIIRS_','').replace('_NRT',''));
      cell(tr, number(item.raw_pixels));
      cell(tr, item.catalog_granule_ids.length
        ? `${item.catalog_granule_ids.length} granule interval${item.catalog_granule_ids.length === 1 ? '' : 's'}`
        : 'No exact interval match; acquisition status unknown');
      cell(tr, paired ? (paired.candidate_provider_minutes[index].active_fire_granule_ids.length
        ? 'L2 product catalogued in exact interval' : 'No exact L2 interval match; status unknown')
        : 'Catalog unavailable');
      el('catalog-candidates').append(tr);
    }
    const count = report.population;
    el('catalog-summary').textContent = `${count.catalog_granules} granules intersect the ${report.query_bbox_wgs84} WGS84 search box; ${count.temporally_matched_candidate_provider_minutes}/${count.candidate_provider_minutes} archived provider-minute groups have an exact catalog interval match. This is not cell-level observation opportunity, and unmatched minutes are not failed observations.`;
    el('catalog-provenance').textContent = `NASA CMR ${report.source_queries.map(query => `${query.product} v${query.collection_version}: ${query.cmr_hits} records, response SHA-256 ${query.response_sha256}`).join(' · ')}. Queried ${report.catalog_fetched_at}; granule files were not downloaded. Source revisions and acquisition-minute conventions can change this comparison. No negative detection count is calculated.`;
    el('catalog-status').textContent = 'CMR catalog context loaded.';
  } catch (error) {
    el('catalog-status').textContent = `CMR catalog context unavailable: ${error.message}`;
    el('pair-status').textContent = 'Active-fire product catalog comparison requires geolocation context.';
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
startAnnual();
startCatalog();
