import {validatePilot, selectPilot} from './analytics-data.mjs';

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
      ? `Experimental next-scan collection count only; ${report.model_research.degenerate_training_target ? 'training target has no variation, so comparison is unsupported' : 'comparison is research-only'}; no validated wildfire prediction.`
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
