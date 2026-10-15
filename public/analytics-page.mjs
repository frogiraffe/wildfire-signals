import {buildResearchReport,formatResearchReport} from './research-report.mjs';
import {investigationManifest} from './investigation-manifest.mjs';
import {historicalAudit} from './historical-audit.mjs';
import {renderSpatialGrid} from './historical-grid.mjs';
import {historicalTimeline,renderHistoricalTimeline} from './historical-timeline.mjs';
import {compareHistoricalEvidence,historicalEvidenceCsv} from './historical-evidence.mjs';
import {validatePilot, selectPilot, validateEnvironment, selectEnvironment,
  environmentalVariables, validateCatalog, validatePairedCatalog,
  validateAnnualArchive, selectAnnualArchive, annualYearSummary,
  annualVariables, validateSpatialRecurrence, selectSpatialRecurrence,
  validateStandardReadiness, validateStaticSensitivity, selectStaticSensitivity,
  validateFrapCohort} from './analytics-data.mjs';

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
  const exportEvidence = (filename,content,type) => {
    const link=document.createElement('a');
    const url=URL.createObjectURL(new Blob([content],{type}));
    link.href=url;link.download=filename;link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
  let evidenceComparison=null;
  const renderEvidenceComparison = () => {
    const selection={from:el('annual-from').value,to:el('annual-to').value,
      provider:el('annual-provider').value,variable:el('annual-variable').value};
    try {
      evidenceComparison=compareHistoricalEvidence(available,selection);
      el('evidence-comparison-rows').replaceChildren();
      for(const row of evidenceComparison.rows) {
        const tr=document.createElement('tr');
        for (const val of [row.region,row.monthsWithCandidates,row.rawPixels,
          row.candidateCellHours,row.weatherObservedMonths,'No']) cell(tr,String(val));
        el('evidence-comparison-rows').append(tr);
      }
      el('evidence-comparison-quality').textContent=evidenceComparison.interpretation;
      el('evidence-comparison-provenance').textContent=evidenceComparison.rows.map(row=>
        row.region+': SHA-256 '+row.evidenceSha256).join(' · ');
      el('evidence-comparison-json').disabled=false;
      el('evidence-comparison-csv').disabled=false;
    } catch(error) {
      evidenceComparison=null;
      el('evidence-comparison-rows').replaceChildren();
      el('evidence-comparison-quality').textContent='Comparison unavailable: '+error.message;
      el('evidence-comparison-provenance').textContent='';
      el('evidence-comparison-json').disabled=true;
      el('evidence-comparison-csv').disabled=true;
    }
  };
  el('evidence-comparison-json').addEventListener('click',()=>{
    if (evidenceComparison) exportEvidence('wildfire-historical-evidence.json',
      JSON.stringify(evidenceComparison,null,2),'application/json');
  });
  el('evidence-comparison-csv').addEventListener('click',()=>{
    if (evidenceComparison) exportEvidence('wildfire-historical-evidence.csv',
      historicalEvidenceCsv(evidenceComparison),'text/csv;charset=utf-8');
  });
  let timelineMetric='raw_pixels';
  const drawTimeline=()=>{
    try {
      const report=historicalTimeline(available,{
        from:el('annual-from').value,to:el('annual-to').value,
        provider:el('annual-provider').value,metric:timelineMetric});
      renderHistoricalTimeline(el('historical-timeline-chart'),report);
      const tbody=el('historical-timeline-rows');tbody.replaceChildren();
      for(const point of report.points){
        const tr=document.createElement('tr');
        cell(tr,point.month);
        for (const value of point.values) cell(tr,value===null?'Unknown':number(value));
        cell(tr,'Satellite opportunity unverified');tbody.append(tr);
      }
      el('historical-timeline-status').textContent=report.note+' Sources: '+
        report.series.map(s=>s.label+' '+s.sha256).join(' · ');
    } catch(error){
      el('historical-timeline-chart').replaceChildren();
      el('historical-timeline-rows').replaceChildren();
      el('historical-timeline-status').textContent='Timeline unavailable: '+error.message;
    }
  };
  el('timeline-metric').addEventListener('change',event=>{
    timelineMetric=event.target.value;drawTimeline();
  });
  const renderSelected = () => {
    const chosen = available.find(item => item.pilot.id === el('annual-region').value);
    const {report,pilot} = chosen;
    el('annual-provenance').textContent = `${pilot.label}: ${report.population.country_source_rows.toLocaleString()} rows in ${report.population.source_files} NASA annual country files; ${report.population.selected_raw_pixels.toLocaleString()} selected pixels in a ${report.region.radius_km} km circle. ${report.population.station_source_rows.toLocaleString()} rows in ${report.population.weather_files} NOAA station files; ${report.population.weather_matched_provider_hours_temperature_c}/${report.population.candidate_provider_hours} positive sensor-hours have prior station temperature. NASA and NOAA files are revised; original first availability is unknown. Evidence SHA-256: ${report.evidence_sha256}. Source file hashes and revisions are in the download. Weather license: ${report.weather_license}. No independently confirmed wildfire outcome.`;
    const center=report.region;
    const mapParams=new URLSearchParams({
      lat:String(center.latitude),lon:String(center.longitude),zoom:'9',hours:'72',
      rlat:String(center.latitude),rlon:String(center.longitude),rr:String(center.radius_km)
    });
    el('historical-navigation-link').href='./index.html#'+mapParams.toString();
    el('historical-navigation-status').textContent=
      pilot.label+' · '+center.radius_km+' km archived study circle · '+center.latitude+
      ', '+center.longitude+'. The linked global map shows recent source observations only.';
    el('annual-download').href = pilot.url;
    try {
      drawAnnual(report);
      renderEvidenceComparison();
      drawTimeline();
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

async function startSpatial() {
  try {
    const response = await fetch('./data/turkey-spatial-recurrence-2023-2025.json', {cache:'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const report = validateSpatialRecurrence(await response.json());
    el('spatial-region').replaceChildren();
    for (const item of report.regions) {
      const option = document.createElement('option');
      option.value = item.region.region_id;
      option.textContent = item.region.region_id.replace('_25KM','');
      el('spatial-region').append(option);
    }
    const label = {
      observed_thermal_candidate: 'Observed candidate',
      recurrently_observed_candidate: 'Recurring candidate',
      potential_static_thermal_source: 'Potential static source (unverified)'
    };
    const render = () => {
      const item = selectSpatialRecurrence(report, el('spatial-region').value);
      const audit=historicalAudit(report,el('spatial-region').value);
      const auditRows=[
        ['Archived thermal pixels',number(audit.totalPixels)],
        ['Pixels represented in published research bins',number(audit.mappedPixels)],
        ['Pixels outside published bins',number(audit.unmappedPixels)],
        ['Published geographic bins',number(audit.publishedBins)],
        ['Satellite acquisition exposure','Unverified'],
        ['Independently validated wildfire outcomes','None established'],
        ['Independent static-source identification','Not verified'],
        ['Evidence SHA-256',audit.sourceSha256]
      ];
      const auditList=el('spatial-audit-values');auditList.replaceChildren();
      for(const [key,value] of auditRows){
        const dt=document.createElement('dt');dt.textContent=key;
        const dd=document.createElement('dd');dd.textContent=value;
        auditList.append(dt,dd);
      }
      el('spatial-audit-warning').textContent=audit.caution;
      const inspect = id => {
        const bin=item.published_bins.find(row=>row.bin_id===id);
        if(!bin)return;
        el('spatial-cell-summary').textContent=id+' · '+bin.classification+
          ' · research candidate only; independent source identity '+bin.source_identity_status+'.';
        const dl=el('spatial-cell-evidence');dl.replaceChildren();
        const entries=[
          ['WGS84 bounds',bin.bounds_wgs84.join(', ')],
          ['Archived thermal pixels',number(bin.raw_pixels)],
          ['Observed UTC dates / years',bin.distinct_dates+' / '+bin.distinct_years],
          ['First / last observation',bin.first_observed_at+' / '+bin.last_observed_at],
          ['NOAA-20 / S-NPP pixels',(bin.provider_counts?.VIIRS_NOAA20_STANDARD??0)+' / '+(bin.provider_counts?.VIIRS_SNPP_STANDARD??0)],
          ['Both-sensor dates',number(bin.sensor_agreement_dates)],
          ['Classification basis',bin.classification_basis],
          ['Independent classification',bin.independently_classified?'Yes':'No'],
          ['Source identity',bin.source_identity_status],
          ['Satellite observation opportunity','Unknown']
        ];
        for(const [label,value] of entries){
          const dt=document.createElement('dt');dt.textContent=label;
          const dd=document.createElement('dd');dd.textContent=value??'Unknown';
          dl.append(dt,dd);
        }
      };
      renderSpatialGrid(el('spatial-grid-map'),item,el('spatial-grid-filter').value,inspect,el('spatial-grid-sensor').value);
      const displayed=item.published_bins.filter(bin=>(el('spatial-grid-filter').value==='all'||
        bin.classification===el('spatial-grid-filter').value) &&
        (el('spatial-grid-sensor').value==='all'||(bin.provider_counts?.[el('spatial-grid-sensor').value]??0)>0));
      if(displayed.length)inspect(displayed[0].bin_id);
      else {el('spatial-cell-summary').textContent='No mapped cells match the current filter.';
        el('spatial-cell-evidence').replaceChildren();}
      el('spatial-summary').textContent = `${number(item.selected_raw_pixels)} archived pixels in ${number(item.occupied_bins)} occupied 0.01° bins; ${number(item.recurrently_observed_bins)} bins recur on multiple UTC dates, ${number(item.bins_seen_in_multiple_years)} span multiple years, ${number(item.potential_static_source_bins)} meet a source-based potential-static review rule. ${number(item.unpublished_bins)} other bins are summarized only. These are neither fire counts nor fire rates.`;
      el('spatial-quality').textContent = `FIRMS confidence: low ${number(item.confidence_counts.l ?? 0)}, nominal ${number(item.confidence_counts.n ?? 0)}, high ${number(item.confidence_counts.h ?? 0)}; day ${number(item.daynight_counts.D ?? 0)}, night ${number(item.daynight_counts.N ?? 0)}; source type 2 ${number(item.source_type_counts['2'] ?? 0)}. Historical source type can be wrong; independent source identity and acquisition opportunity are unknown.`;
      el('spatial-year-quality').replaceChildren();
      for (const year of item.yearly_quality_rows) {
        const tr = document.createElement('tr');
        for (const value of [year.year, number(year.raw_pixels),
          number(year.source_type_counts['0'] ?? 0), number(year.source_type_counts['2'] ?? 0),
          number(year.source_type_counts['3'] ?? 0),
          `${number(year.confidence_counts.l ?? 0)} / ${number(year.confidence_counts.n ?? 0)} / ${number(year.confidence_counts.h ?? 0)}`,
          `${number(year.daynight_counts.D ?? 0)} / ${number(year.daynight_counts.N ?? 0)}`]) cell(tr,value);
        el('spatial-year-quality').append(tr);
      }
      el('spatial-bins').replaceChildren();
      el('spatial-chart').replaceChildren();
      const maximum = Math.max(1, ...item.published_bins.map(bin => bin.raw_pixels));
      for (const bin of item.published_bins) {
        const tr = document.createElement('tr');
        for (const value of [bin.bin_id, number(bin.raw_pixels),
          `${number(bin.distinct_dates)} / ${number(bin.distinct_years)}`,
          number(bin.sensor_agreement_dates), number(bin.source_type_counts['2'] ?? 0),
          label[bin.classification]]) cell(tr,value);
        el('spatial-bins').append(tr);
        const bar = document.createElement('div'); bar.className = 'analytics-bar';
        const column = document.createElement('span');
        column.style.height = `${Math.max(2, Math.round(110 * bin.raw_pixels / maximum))}px`;
        const tick = document.createElement('small'); tick.textContent = bin.bin_id;
        bar.title = `${bin.bin_id}: ${bin.raw_pixels} archived pixels, ${bin.distinct_dates} dates; ${label[bin.classification]}; source identity unresolved`;
        bar.append(column,tick); el('spatial-chart').append(bar);
      }
      el('spatial-chart').setAttribute('aria-label', `${item.region.region_id}: top ${item.published_bins.length} coarsened bins by recurring dates and pixel count; these are thermal candidates, not fires`);
    };
    el('spatial-region').addEventListener('change', render);
    el('spatial-grid-filter').addEventListener('change', render);
    el('spatial-grid-sensor').addEventListener('change', render);
    el('spatial-provenance').textContent = `${number(report.population.country_source_rows)} rows in ${report.population.source_files} original NASA files, SHA-256 pinned in the download. 0.01° bins are research grouping, not sensor footprints. NASA's Static Thermal Anomalies Mask is reference only and was not redistributed or joined. The historical FIRMS type field has known defects. No independent non-vegetation or wildfire classification, valid no-detection population, cloud/quality mask or operational model is present. Evidence SHA-256: ${report.evidence_sha256}.`;
    render();
    el('spatial-status').textContent = 'Spatial recurrence evidence loaded.';
  } catch (error) {
    el('spatial-status').textContent = `Spatial recurrence unavailable: ${error.message}`;
  }
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

async function startStandardReadiness() {
  try {
    const response = await fetch('./data/antalya-standard-granule-readiness-2025-01-06-07.json',
      {cache:'no-store'});
    if (!response.ok) throw new Error(`Report unavailable (${response.status})`);
    const report = validateStandardReadiness(await response.json());
    el('standard-readiness-summary').textContent = `${report.population.geolocation_granules} standard L1 and ${report.population.active_fire_granules} standard L2 catalog entries form ${report.population.paired_intervals} exact NOAA-20 intervals. The two-day 25 km Antalya archive has ${report.population.archived_noaa20_pixels} NOAA-20 raw pixel. Catalog entries are not verified cell exposure.`;
    el('standard-readiness-days').replaceChildren();
    for (const day of report.daily_rows) {
      const row = document.createElement('tr');
      for (const value of [day.date_utc, number(day.catalogued_paired_intervals),
        number(day.archived_noaa20_pixels), day.observation_state === 'archived_candidate'
          ? 'Archived thermal candidate; physical event unresolved'
          : 'No archived record; observation opportunity unknown']) cell(row,value);
      el('standard-readiness-days').append(row);
    }
    el('standard-readiness-gates').textContent = 'Occurrence model readiness: blocked. Cell-level exposure, independent positive and negative fire outcomes, decision-time weather availability and a separated evaluation cohort are absent. No model was trained.';
    el('standard-readiness-provenance').textContent = `NASA CMR ${report.source_queries.map(query => `${query.product} v${query.version}: ${query.cmr_hits} entries, response SHA-256 ${query.response_sha256}`).join(' · ')}. Snapshot ${report.cmr_fetched_at}; annual source report SHA-256 ${report.annual_report_sha256}; reproducible report SHA-256 ${report.evidence_sha256}. Original granule contents were not inspected.`;
    el('standard-readiness-status').textContent = 'Standard product research evidence loaded.';
  } catch (error) {
    el('standard-readiness-status').textContent = `Standard product evidence unavailable: ${error.message}`;
    el('standard-readiness-days').replaceChildren();
  }
}

async function startSensitivity() {
  try {
    const response = await fetch('./data/turkey-static-sensitivity-2023-2025.json',
      {cache:'no-store'});
    if (!response.ok) throw new Error(`Report unavailable (${response.status})`);
    const report = validateStaticSensitivity(await response.json());
    const selector = el('sensitivity-region');
    selector.replaceChildren();
    for (const region of report.regions) {
      const option = document.createElement('option'); option.value = region.region_id;
      option.textContent = region.region_id.replace('_25KM',''); selector.append(option);
    }
    const draw = () => {
      const region = selectStaticSensitivity(report, selector.value);
      el('sensitivity-summary').textContent = `${region.all_raw_pixels.toLocaleString()} original archived pixels; ${region.unresolved_recurrent_raw_pixels.toLocaleString()} lie in ${region.unresolved_recurrent_bins.length} unresolved recurrent bins; ${region.other_raw_pixels.toLocaleString()} remain other unverified candidates. Independently established non-wildfire exclusions: 0.`;
      el('sensitivity-rows').replaceChildren();
      for (const item of region.year_sensor_rows) {
        const row = document.createElement('tr');
        for (const value of [item.year, item.provider === 'VIIRS_NOAA20_STANDARD' ? 'NOAA-20' : 'Suomi NPP',
          number(item.all_raw_pixels), number(item.unresolved_recurrent_raw_pixels),
          number(item.other_raw_pixels), number(item.unresolved_source_type2_raw_pixels)]) cell(row,value);
        el('sensitivity-rows').append(row);
      }
      const years = [...new Set(region.year_sensor_rows.map(item => item.year))];
      const annual = years.map(year => {
        const rows = region.year_sensor_rows.filter(item => item.year === year);
        return {year, all: rows.reduce((n,item) => n+item.all_raw_pixels,0),
          unresolved: rows.reduce((n,item) => n+item.unresolved_recurrent_raw_pixels,0)};
      });
      const maximum = Math.max(1,...annual.map(item => item.all));
      el('sensitivity-chart').replaceChildren();
      for (const item of annual) {
        const bar = document.createElement('div'); bar.className = 'analytics-bar';
        const count = document.createElement('strong'); count.textContent = number(item.all);
        const column = document.createElement('span');
        column.style.height = `${Math.max(2,Math.round(130*item.all/maximum))}px`;
        const share = item.all ? Math.round(100*item.unresolved/item.all) : 0;
        column.style.background = `linear-gradient(to top,#e8ad70 ${share}%,#7cc6be ${share}%)`;
        const label = document.createElement('small'); label.textContent = String(item.year);
        bar.title = `${item.year}: ${item.all} archived pixels, ${item.unresolved} unresolved recurrent-bin pixels; satellite exposure unknown`;
        bar.append(count,column,label); el('sensitivity-chart').append(bar);
      }
      el('sensitivity-chart').setAttribute('aria-label', `${region.region_id}: annual original pixels, amber unresolved recurrent bins and teal other unverified candidates; unknown satellite exposure`);
    };
    selector.value = report.regions[0].region_id;
    selector.addEventListener('change',draw);
    draw();
    el('sensitivity-provenance').textContent = `${number(report.population.country_source_rows)} rows from ${report.population.source_files} SHA-256 verified NASA originals; ${number(report.population.selected_raw_pixels)} selected pixels. Source recurrence report SHA-256 ${report.spatial_report_sha256}; aggregate SHA-256 ${report.evidence_sha256}. FIRMS source type and recurrent location are research cues, not independently verified physical identities.`;
    el('sensitivity-status').textContent = 'Real source sensitivity loaded.';
  } catch (error) {
    el('sensitivity-status').textContent = `Source sensitivity unavailable: ${error.message}`;
    el('sensitivity-chart').replaceChildren(); el('sensitivity-rows').replaceChildren();
  }
}

async function startFrapCohort() {
  try {
    const response = await fetch('./data/sacramento-frap-outcome-cohort-2023-2025.json',
      {cache:'no-store'});
    if (!response.ok) throw new Error(`Report unavailable (${response.status})`);
    const report = validateFrapCohort(await response.json());
    el('frap-summary').textContent = `${report.population.source_perimeters} official mapped perimeters intersect the fixed study box in 2023–2025. ${report.population.ground_or_air_suppression_evidence} have ground/air GPS mapping plus a wildfire suppression objective; ${report.population.other_method_or_objective_unknown} have unresolved method or objective for this stronger evidence category. Verified fire-negative units: 0. Occurrence model: ineligible.`;
    el('frap-cases').replaceChildren();
    for (const item of report.cases) {
      const row = document.createElement('tr');
      for (const value of [`${item.source_year} · ${item.source_name ?? 'Unnamed'}`,
        item.source_alarm_date_calendar ?? 'Unknown', item.source_agency ?? 'Unknown',
        item.source_method, item.evidence_status === 'ground_or_air_mapped_suppression_perimeter'
          ? 'GPS-mapped suppression perimeter; event lineage unresolved'
          : 'Agency perimeter; independence or objective unresolved']) cell(row,value);
      el('frap-cases').append(row);
    }
    el('frap-provenance').textContent = `CAL FIRE FRAP ${report.source_revision}; source GeoJSON SHA-256 ${report.source_geojson_sha256}, count response SHA-256 ${report.source_count_sha256}, layer metadata SHA-256 ${report.source_metadata_sha256}, report SHA-256 ${report.evidence_sha256}. Final perimeter geometry, source dates and collection methods may be revised; first record availability is unknown. The layer omits small or undocumented fires and supplies no verified negative population.`;
    el('frap-status').textContent = 'Official perimeter evidence loaded.';
  } catch (error) {
    el('frap-status').textContent = `Official perimeter evidence unavailable: ${error.message}`;
    el('frap-cases').replaceChildren();
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


function applyUnifiedInvestigation() {
  const study=el('unified-study').value;
  const sensor=el('unified-sensor').value;
  if(!['ANTALYA_25KM','DALAMAN_25KM'].includes(study) ||
      !['all','VIIRS_NOAA20_STANDARD','VIIRS_SNPP_STANDARD'].includes(sensor)) {
    el('unified-status').textContent='Invalid study or sensor; no view updated.';
    return;
  }
  const selections=[['annual-region',study],['spatial-region',study],
    ['annual-provider',sensor],['spatial-grid-sensor',sensor]];
  for (const [id,value] of selections) {
    const input=el(id);
    if (!input || ![...input.options].some(option=>option.value===value)) {
      el('unified-status').textContent='Archive data for this study is not yet available; previous selection kept.';
      return;
    }
  }
  for (const [id,value] of selections) {
    const input=el(id);input.value=value;
    input.dispatchEvent(new Event('change',{bubbles:true}));
  }
  el('unified-status').textContent=
    'Applied '+study.replace('_25KM','')+' and '+(sensor==='all'?'both VIIRS sensors':sensor)+
    ' to annual, temporal and spatial evidence. Grid bins still represent the full 2023–2025 archive; weather studies use their own stations and periods.';
}
el('unified-apply').addEventListener('click',applyUnifiedInvestigation);
el('unified-export').addEventListener('click',()=>{
  try {
    const manifest=investigationManifest({
      study:el('annual-region').value,sensor:el('annual-provider').value,
      from:el('annual-from').value,to:el('annual-to').value,
      metric:el('timeline-metric').value,gridFilter:el('spatial-grid-filter').value
    });
    const blob=new Blob([JSON.stringify(manifest,null,2)],{type:'application/json'});
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;link.download='wildfire-investigation-selection.json';link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    el('unified-status').textContent='Investigation selection manifest prepared. It records source paths and filters, not the source datasets.';
  } catch(error) {el('unified-status').textContent='Export unavailable: '+error.message;}
});

let researchReportUrl=null;
el('research-report-build').addEventListener('click',async()=>{
  const preview=el('research-report-preview'),download=el('research-report-download');
  preview.hidden=false;download.hidden=true;
  preview.textContent='Validating original archive evidence…';
  try{
    const study=el('annual-region').value;
    const id=study==='ANTALYA_25KM'?'antalya':study==='DALAMAN_25KM'?'dalaman':null;
    if(!id)throw new Error('Unknown study');
    const paths=['./data/'+id+'-annual-context-2023-2025.json',
      './data/turkey-spatial-recurrence-2023-2025.json'];
    const reports=await Promise.all(paths.map(async path=>{
      const response=await fetch(path,{cache:'no-store'});
      if(!response.ok)throw new Error('Evidence unavailable: '+path);
      return response.json();
    }));
    const report=buildResearchReport(reports[0],reports[1],{
      study,sensor:el('annual-provider').value,
      from:el('annual-from').value,to:el('annual-to').value,
      metric:el('timeline-metric').value,gridFilter:el('spatial-grid-filter').value});
    preview.textContent=formatResearchReport(report);
    if(researchReportUrl)URL.revokeObjectURL(researchReportUrl);
    researchReportUrl=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],
      {type:'application/json'}));
    download.href=researchReportUrl;download.hidden=false;
    el('unified-status').textContent='Evidence report verified against both archived source contracts. Download includes source receipts and limitations.';
  }catch(error){
    preview.textContent='Report unavailable: '+error.message;
    el('unified-status').textContent='Research report was not generated: '+error.message;
  }
});

start();
startEnvironment();
startAnnual();
startSpatial();
startCatalog();
startStandardReadiness();
startSensitivity();
startFrapCohort();
