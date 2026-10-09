import * as maplibregl from 'https://unpkg.com/maplibre-gl@6.13.0/dist/maplibre-gl.mjs';
import {MESSAGES, parseState, stateHash, visible, effectiveStatus, featureCollection} from './map-state.mjs';

const state = parseState(location.hash);
let snapshot = {manifest:{data_status:'unknown'},events:[],incidents:[],matches:[],sources:[],details:{}};
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

function showRecord(kind, id) {
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
      [msg.modified, item.modified_at || item.last_seen_at], [msg.location, `${item.latitude}, ${item.longitude}`]];
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
  el('detail').hidden = false;
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
  el('candidate-count').textContent = events.length.toLocaleString(state.lang);
  el('incident-count').textContent = incidents.length.toLocaleString(state.lang);
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
map.on('moveend',saveState);

for (const key of ['language','hours','source','kind']) el(key).addEventListener('change',event => {
  state[key === 'language' ? 'lang' : key] = key === 'hours' ? Number(event.target.value) : event.target.value;
  saveState(); draw();
});
el('share').addEventListener('click',async () => {
  saveState(); await navigator.clipboard.writeText(location.href);
});
el('detail-close').addEventListener('click',() => {el('detail').hidden = true;});
window.addEventListener('keydown',event => {if (event.key === 'Escape') el('detail').hidden = true;});
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
