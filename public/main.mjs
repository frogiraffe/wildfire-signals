import * as maplibregl from 'https://unpkg.com/maplibre-gl@6.13.0/dist/maplibre-gl.mjs';
import {MESSAGES, parseState, stateHash, visible, effectiveStatus, featureCollection} from './map-state.mjs';
import {summarizeArea, investigationLeads} from './area-analysis.mjs';
import {incidentTimeline} from './incident-timeline.mjs';
import {fetchNwsWeather, forecastChanges} from './weather-context.mjs';
import {recordAnalysis} from './analysis-answers.mjs';

const state = parseState(location.hash);
let snapshot = {manifest:{data_status:'unknown'},events:[],incidents:[],matches:[],sources:[],details:{}};
let weatherController = null;
const el = id => document.getElementById(id);
const map = new maplibregl.Map({container:'map',
  style:'https://tiles.openfreemap.org/styles/liberty', center:[state.lon,state.lat], zoom:state.zoom,
  attributionControl:true});
map.addControl(new maplibregl.NavigationControl(), 'bottom-right');

function translate() {
  document.documentElement.lang = state.lang;
  for (const node of document.querySelectorAll('[data-i18n]'))
    node.textContent = MESSAGES[state.lang][node.dataset.i18n];
  el('language').value = state.lang;
  el('hours').value = String(state.hours);
  el('source').value = state.source;
  el('kind').value = state.kind;
  el('detail-close').setAttribute('aria-label',MESSAGES[state.lang].close);
  document.title = `${MESSAGES[state.lang].title} — public map`;
}

function saveState() {
  const center = map.getCenter();
  state.lat = Number(center.lat.toFixed(3));
  state.lon = Number(center.lng.toFixed(3));
  state.zoom = Number(map.getZoom().toFixed(2));
  history.replaceState(null, '', stateHash(state));
}

function stopWeatherRequest() {
  weatherController?.abort();
  weatherController = null;
}

function renderWeather(container, forecast, msg) {
  container.replaceChildren();
  const meta = document.createElement('p');
  meta.textContent = `${msg.weatherUpdated}: ${forecast.updatedAt} · ${msg.weatherReceived}: ${forecast.receivedAt}`;
  container.append(meta);
  if (forecast.stale) {
    const warning = document.createElement('p'); warning.textContent = msg.weatherStale;
    container.append(warning);
  }
  const changes = forecastChanges(forecast);
  if (changes.length) {
    const analysis = document.createElement('section');
    analysis.className = 'weather-change-analysis';
    const title = document.createElement('h4'); title.textContent = msg.weatherChangeTitle;
    const scope = document.createElement('p'); scope.textContent = msg.weatherChangeScope;
    const changeList = document.createElement('ul');
    const signed = (value, unit) => value === null ? msg.weatherMissing
      : `${value > 0 ? '+' : ''}${Math.round(value * 10) / 10} ${unit}`;
    for (const row of changes) {
      const item = document.createElement('li');
      const time = document.createElement('strong');
      time.textContent = msg.weatherHour.replace('{hours}',row.hours);
      const wind = document.createElement('span');
      wind.textContent = `${msg.weatherWind}: ${signed(row.windKmh,'km/h')} · ` +
        `${msg.weatherGust}: ${signed(row.gustKmh,'km/h')} · ` +
        `${msg.weatherTurn}: ${signed(row.directionTurnDeg,'°')}`;
      const air = document.createElement('span');
      air.textContent = `${msg.weatherTemp}: ${signed(row.temperatureC,'°C')} · ` +
        `${msg.weatherHumidity}: ${signed(row.humidityPercent,'%')}`;
      item.append(time,wind,air); changeList.append(item);
    }
    const caveat = document.createElement('p'); caveat.textContent = msg.weatherChangeCaveat;
    analysis.append(title,scope,changeList,caveat);
    container.append(analysis);
  }
  const list = document.createElement('ol');
  for (const row of forecast.rows) {
    const item = document.createElement('li');
    const time = document.createElement('strong');
    time.textContent = `${msg.weatherHour.replace('{hours}',row.hours)} · ${row.validAt}`;
    const number = (value, unit) => value === null ? msg.weatherMissing : `${Math.round(value)} ${unit}`;
    const wind = document.createElement('span');
    const direction = row.directionDeg === null ? msg.weatherMissing : `${Math.round(row.directionDeg)}°`;
    wind.textContent = `${msg.weatherWind}: ${number(row.windKmh,'km/h')} ` +
      `(${msg.weatherFrom} ${direction}) · ${msg.weatherGust}: ${number(row.gustKmh,'km/h')}`;
    const air = document.createElement('span');
    air.textContent = `${msg.weatherTemp}: ${number(row.temperatureC,'°C')} · ` +
      `${msg.weatherHumidity}: ${number(row.humidityPercent,'%')}`;
    const rain = document.createElement('span');
    rain.textContent = `${msg.weatherRain}: ${row.rain ? `${row.rain.mm} mm ` +
      `(${msg.weatherRainWindow} ${row.rain.start} – ${row.rain.end})` : msg.weatherMissing}`;
    item.append(time,wind,air,rain); list.append(item);
    const detail = document.createElement('details');
    const summary = document.createElement('summary'); summary.textContent = msg.weatherIntervals;
    const intervals = document.createElement('dl');
    for (const [label,key] of [[msg.weatherWind,'windKmh'],[msg.weatherFrom,'directionDeg'],
      [msg.weatherGust,'gustKmh'],[msg.weatherTemp,'temperatureC'],
      [msg.weatherHumidity,'humidityPercent']]) {
      const valid = row.validity[key];
      if (!valid) continue;
      const dt = document.createElement('dt'); dt.textContent = label;
      const dd = document.createElement('dd'); dd.textContent = `${valid.start} – ${valid.end}`;
      intervals.append(dt,dd);
    }
    detail.append(summary,intervals); item.append(detail);
  }
  container.append(list);
  const footnote = document.createElement('p'); footnote.textContent = msg.weatherFootnote;
  const source = document.createElement('a');
  source.href = forecast.sourceUrl; source.textContent = 'NOAA / NWS';
  source.target = '_blank'; source.rel = 'noopener noreferrer';
  container.append(footnote,source);
}

function showWeather(box, incident, msg) {
  if (incident.provider !== 'nifc_wfigs') return;
  const section = document.createElement('section'); section.className = 'weather-context';
  const heading = document.createElement('h3'); heading.textContent = msg.weatherTitle;
  const scope = document.createElement('p'); scope.textContent = msg.weatherScope;
  const content = document.createElement('div'); content.setAttribute('role','status');
  content.textContent = msg.weatherLoading;
  section.append(heading,scope,content); box.append(section);
  const controller = new AbortController(); weatherController = controller;
  const timeout = setTimeout(() => controller.abort(),12_000);
  fetchNwsWeather(incident.latitude,incident.longitude,{signal:controller.signal})
    .then(forecast => {
      if (weatherController === controller && !el('detail').hidden)
        renderWeather(content,forecast,msg);
    })
    .catch(() => {
      if (weatherController === controller && !el('detail').hidden)
        content.textContent = msg.weatherUnavailable;
    })
    .finally(() => clearTimeout(timeout));
}

function showAnalysis(box, kind, item, msg) {
  const result = recordAnalysis(item,kind,snapshot.manifest,snapshot.sources);
  const section = document.createElement('section');
  section.className = 'analysis-answers';
  const title = document.createElement('h3'); title.textContent = msg.analysisTitle;
  const scope = document.createElement('p'); scope.textContent = msg.analysisScope;
  const quality = document.createElement('p');
  quality.textContent = `${msg.analysisEvidence}: ${msg[result.quality]} · ` +
    `${msg.analysisSourceTime}: ${result.sourceTime || msg.weatherMissing}`;
  const list = document.createElement('ol');
  for (const [question,answer,reason] of [
    ['analysisWhere',result.presence,null],
    ['analysisIgnition',result.ignition,result.ignitionReason],
    ['analysisSpread',result.spread,result.spreadReason],
    ['analysisEnding',result.ending,result.endingReason]]) {
    const row = document.createElement('li');
    const heading = document.createElement('h4'); heading.textContent = msg[question];
    const statement = document.createElement('strong'); statement.textContent = msg[answer];
    row.append(heading,statement);
    if (reason) {
      const explanation = document.createElement('p'); explanation.textContent = msg[reason];
      row.append(explanation);
    }
    list.append(row);
  }
  section.append(title,scope,quality,list); box.append(section);
}

function showRecord(kind, id) {
  stopWeatherRequest();
  const msg = MESSAGES[state.lang];
  const item = kind === 'candidate' ? snapshot.events.find(x => x.event_id === id)
    : snapshot.incidents.find(x => `${x.provider}:${x.official_id}` === id);
  if (!item) return;
  const box = el('detail-content');
  box.replaceChildren();
  const title = document.createElement('h2');
  title.textContent = kind === 'candidate' ? msg.candidates : item.name || msg.incidents;
  box.append(title);
  const note = document.createElement('p');
  note.textContent = kind === 'candidate' ? msg.candidate : msg.agency;
  box.append(note);
  const rows = kind === 'candidate' ? [
    [msg.id, item.event_id], [msg.observed, item.observed_at], [msg.received, item.received_at],
    [msg.sources, (item.sources || []).join(', ')], [msg.location, `${item.latitude}, ${item.longitude}`],
    [msg.thermal, item.thermal_pixel_trend?.direction || '—'],
    [msg.detections, item.detection_count ?? '—'], [msg.aggregation,item.aggregation || '—']]
    : [[msg.id, item.official_id], [msg.provider, item.provider], [msg.kind, item.incident_kind],
      [msg.modified, item.modified_at || item.last_seen_at], [msg.location, `${item.latitude}, ${item.longitude}`],
      ...(item.agency_status ? [[msg.agencyStatus, msg[`status${item.agency_status}`] || item.agency_status]] : [])];
  const list = document.createElement('dl');
  for (const [label,value] of rows) {
    const dt = document.createElement('dt'), dd = document.createElement('dd');
    dt.textContent = label; dd.textContent = String(value || '—'); list.append(dt,dd);
  }
  box.append(list);
  const links = kind === 'candidate' ? (snapshot.matches || []).filter(x => x.event_id === id) : [];
  if (links.length) {
    const matched = document.createElement('p');
    matched.textContent = links.some(x => x.status === 'ambiguous') ? msg.ambiguous : msg.provisional;
    box.append(matched);
    const list = document.createElement('ul');
    for (const link of links) {
      const row = document.createElement('li');
      row.textContent = `${link.provider}: ${link.official_id} · ${link.distance_km} km`;
      list.append(row);
    }
    box.append(list);
  }
  showAnalysis(box,kind,item,msg);
  el('detail').hidden = false;
  if (kind === 'incident') showWeather(box,item,msg);
  if (kind === 'incident') {
    const heading = document.createElement('h3'); heading.textContent = msg.timelineTitle;
    const scope = document.createElement('p'); scope.textContent = msg.timelineScope;
    box.append(heading,scope);
    const timeline = incidentTimeline(snapshot,item);
    if (!timeline.length) {
      const empty = document.createElement('p'); empty.textContent = msg.timelineEmpty;
      box.append(empty);
    } else {
      const list = document.createElement('ol');
      for (const entry of timeline) {
        const row = document.createElement('li');
        const time = document.createElement('time');
        time.dateTime = entry.seen_at;
        time.textContent = `${new Date(entry.seen_at).toLocaleString(
          state.lang === 'tr' ? 'tr-TR' : 'en-US',
          {timeZone:'UTC',dateStyle:'short',timeStyle:'short'})} UTC`;
        const description = document.createElement('span');
        const change = entry.change === 'first_seen' ? msg.timelineFirst : msg.timelineChanged;
        const agencyStatus = entry.agency_status
          ? ` · ${msg.agencyStatus}: ${msg[`status${entry.agency_status}`] || entry.agency_status}` : '';
        const sourceDate = entry.source_modified_at
          ? ` · ${msg.timelineSourceDate}: ${entry.source_modified_at}` : '';
        description.textContent = `${change}${agencyStatus}${sourceDate}`;
        row.append(time,description); list.append(row);
      }
      box.append(list);
    }
  }
  el('detail-close').focus();
}

function draw() {
  translate();
  const msg = MESSAGES[state.lang];
  const notice = el('notice');
  const dataStatus = effectiveStatus(snapshot.manifest);
  notice.textContent = dataStatus === 'fresh' ? '' : msg[['stale','partial'].includes(dataStatus) ? dataStatus : 'unknown'];
  notice.classList.toggle('show', dataStatus !== 'fresh');
  const {events, incidents} = visible(snapshot,state);
  const analysisEvents = state.kind === 'incident'
    ? visible(snapshot,{...state,kind:'candidate'}).events : events;
  el('candidate-count').textContent = events.length.toLocaleString(state.lang);
  el('incident-count').textContent = incidents.length.toLocaleString(state.lang);
  const bounds = map.getBounds();
  const area = summarizeArea({events:analysisEvents,sources:snapshot.sources},
    {west:bounds.getWest(),east:bounds.getEast(),south:bounds.getSouth(),north:bounds.getNorth()},
    state.hours,new Date());
  const areaAvailable = snapshot.manifest?.last_scan_at != null;
  el('area-candidates').textContent = areaAvailable ? area.candidateCount.toLocaleString(state.lang) : '—';
  el('area-locations').textContent = areaAvailable ? area.locationCount.toLocaleString(state.lang) : '—';
  el('area-repeated').textContent = areaAvailable ? area.repeatedLocationCount.toLocaleString(state.lang) : '—';
  el('area-latest').textContent = areaAvailable && area.latestObservedAt
    ? `${new Date(area.latestObservedAt).toLocaleString(state.lang === 'tr' ? 'tr-TR' : 'en-US',
      {timeZone:'UTC',dateStyle:'short',timeStyle:'short'})} UTC` : '—';
  el('area-comparison').textContent = areaAvailable
    ? `${msg.areaCompare} ${area.comparisonHours} ${msg.areaHours}: ` +
      `${area.recentCount.toLocaleString(state.lang)} / ${area.earlierCount.toLocaleString(state.lang)}` : '';
  el('area-quality').textContent = !areaAvailable ? msg.areaUnavailable : area.sourceProblems.length
    ? `${msg.areaQuality}: ${area.sourceProblems.join(', ')}` : '';
  const leadList = el('lead-list'); leadList.replaceChildren();
  const leads = areaAvailable ? investigationLeads({events:analysisEvents},
    {west:bounds.getWest(),east:bounds.getEast(),south:bounds.getSouth(),north:bounds.getNorth()},
    state.hours,new Date()) : [];
  const leadWarnings = [];
  if (dataStatus === 'stale') leadWarnings.push(msg.leadStale);
  if (area.sourceProblems.length) leadWarnings.push(msg.leadSatellitePartial);
  else if (dataStatus === 'partial') leadWarnings.push(msg.leadPartial);
  if (dataStatus === 'unknown') leadWarnings.push(msg.leadUnknown);
  el('lead-quality').textContent = leadWarnings.join(' ');
  el('lead-empty').hidden = leads.length > 0;
  for (const lead of leads) {
    const row = document.createElement('li');
    const button = document.createElement('button');
    button.type = 'button';
    button.dataset.eventId = lead.eventId;
    const location = document.createElement('strong');
    location.textContent = `${lead.latitude.toFixed(3)}, ${lead.longitude.toFixed(3)}`;
    const evidence = document.createElement('span');
    evidence.textContent = lead.observedHours >= 2
      ? msg.leadRepeated.replace('{hours}',lead.observedHours) : msg.leadSingle;
    const sensors = document.createElement('span');
    sensors.textContent = lead.sources.join(', ');
    const latest = document.createElement('time');
    latest.dateTime = lead.latestObservedAt;
    latest.textContent = `${new Date(lead.latestObservedAt).toLocaleString(
      state.lang === 'tr' ? 'tr-TR' : 'en-US',
      {timeZone:'UTC',dateStyle:'short',timeStyle:'short'})} UTC`;
    button.append(location,evidence,sensors,latest);
    button.addEventListener('click',() => {
      map.easeTo({center:[lead.longitude,lead.latitude],zoom:Math.max(map.getZoom(),8)});
      showRecord('candidate',lead.eventId);
    });
    row.append(button); leadList.append(row);
  }
  el('last-scan').textContent = snapshot.manifest?.last_scan_at || '—';
  const sources = el('source-list'); sources.replaceChildren();
  for (const source of snapshot.sources || []) {
    const row = document.createElement('li'), key = document.createElement('span'), health = document.createElement('em');
    key.textContent = source.key;
    health.textContent = `${source.status} · ${msg.product} ${source.product_age_seconds ?? '—'}s · ${msg.failures} ${source.consecutive_failures ?? 0}`;
    row.append(key,health); sources.append(row);
  }
  if (map.getSource('candidates')) {
    map.getSource('candidates').setData(featureCollection(events,'candidate'));
    map.getSource('incidents').setData(featureCollection(incidents,'incident'));
  }
}

map.on('load', () => {
  map.addSource('candidates',{type:'geojson',data:featureCollection([],'candidate'),cluster:true,clusterRadius:42});
  map.addSource('incidents',{type:'geojson',data:featureCollection([],'incident'),cluster:true,clusterRadius:42});
  for (const [source,color] of [['candidates','#f19b53'],['incidents','#5dc2c7']]) {
    map.addLayer({id:source,type:'circle',source,
      paint:{'circle-color':color,'circle-radius':['case',['has','point_count'],17,8],
        'circle-stroke-color':'#10202a','circle-stroke-width':2,'circle-opacity':.92}});
    map.on('click',source,e => {
      const feature = e.features?.[0]; if (!feature) return;
      if (feature.properties.cluster) {
        map.getSource(source).getClusterExpansionZoom(feature.properties.cluster_id).then(
          zoom => map.easeTo({center:feature.geometry.coordinates,zoom}));
      } else showRecord(feature.properties.kind,feature.properties.id);
    });
    map.on('mouseenter',source,() => {map.getCanvas().style.cursor='pointer';});
    map.on('mouseleave',source,() => {map.getCanvas().style.cursor='';});
  }
  draw();
});
map.on('moveend',() => {saveState();draw();});

for (const key of ['language','hours','source','kind']) el(key).addEventListener('change',event => {
  state[key === 'language' ? 'lang' : key] = key === 'hours' ? Number(event.target.value) : event.target.value;
  saveState(); draw();
});
el('share').addEventListener('click',async () => {
  saveState(); await navigator.clipboard.writeText(location.href);
});
el('detail-close').addEventListener('click',() => {stopWeatherRequest();el('detail').hidden = true;});
window.addEventListener('keydown',event => {if (event.key === 'Escape') {
  stopWeatherRequest(); el('detail').hidden = true;
}});
window.addEventListener('hashchange',() => {Object.assign(state,parseState(location.hash));map.jumpTo({center:[state.lon,state.lat],zoom:state.zoom});draw();});

try {
  const response = await fetch('/api/snapshot',{cache:'no-store'});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  snapshot = await response.json();
  if (snapshot.manifest?.schema_version !== 1) throw new Error('unsupported snapshot');
  const sourceKeys = new Set([...snapshot.sources.map(x => x.key),
    ...snapshot.incidents.map(x => x.provider)]);
  for (const key of [...sourceKeys].sort()) {
    const option = document.createElement('option'); option.value = key; option.textContent = key;
    el('source').append(option);
  }
  if (!sourceKeys.has(state.source)) state.source = 'all';
} catch (error) {
  snapshot.manifest.data_status = 'unknown';
  console.error('Public snapshot unavailable',error);
}
draw();
setInterval(() => {if (!document.hidden) draw();},60_000);
document.addEventListener('visibilitychange',() => {if (!document.hidden) draw();});
