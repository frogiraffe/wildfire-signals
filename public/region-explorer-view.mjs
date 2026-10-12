import {analyzeRegion,circleBoundary,normalLongitude,validRegion} from './region-explorer.mjs';

// UI controller only; all statistical and geographic calculations remain pure and testable.
export function createRegionExplorer({map,state,getSnapshot,saveState,showRecord,messages}) {
  const byId = id => document.getElementById(id);
  let picking = false;
  const picker = byId('region-pick');

  function currentRegion() {
    const region = {latitude:state.regionLat,longitude:state.regionLon,
      radiusKm:state.radiusKm};
    return Number.isFinite(state.regionLat) && Number.isFinite(state.regionLon) &&
      validRegion(region) ? region : null;
  }

  function setRegion(latitude,longitude) {
    state.regionLat = Number(Math.max(-90,Math.min(90,latitude)).toFixed(5));
    state.regionLon = Number(normalLongitude(longitude).toFixed(5));
    picking = false;
    saveState();
    draw();
  }

  function handleMapClick(event) {
    if (!picking) return;
    setRegion(event.lngLat.lat,event.lngLat.lng);
  }

  function draw() {
    const msg = messages[state.lang];
    const region = currentRegion();
    picker.textContent = picking ? msg.regionCancel : msg.regionPick;
    picker.setAttribute('aria-pressed',String(picking));
    map.getCanvas().classList.toggle('region-pick-mode',picking);
    byId('region-radius').value = String(state.radiusKm);
    byId('region-results').hidden = !region;
    byId('region-clear').disabled = !region;
    byId('region-location').textContent = region
      ? `${region.latitude.toFixed(4)}°, ${region.longitude.toFixed(4)}° · ${region.radiusKm} km`
      : msg.regionNoSelection;
    const outline = map.getSource('selected-region');
    if (outline) outline.setData(region ? circleBoundary(region) :
      {type:'FeatureCollection',features:[]});
    if (!region) return;

    const result = analyzeRegion(getSnapshot(),region,state.hours,state.source);
    const missing = !result.available;
    const quality = {current:msg.regionQualityCurrent,stale:msg.regionQualityStale,
      partial:msg.regionQualityPartial,unavailable:msg.regionQualityUnavailable};
    byId('region-quality').textContent = quality[result.quality];
    for (const [id,val] of [
      ['region-candidates',result.candidateCellHours],
      ['region-cells',result.distinctCells],
      ['region-repeat',result.recurringCells]]) {
      byId(id).textContent = missing ? '—' : val.toLocaleString(state.lang);
    }
    const locale = state.lang === 'tr' ? 'tr-TR' : 'en-US';
    byId('region-latest').textContent = result.latestObservedAt
      ? new Date(result.latestObservedAt).toLocaleString(locale,
        {timeZone:'UTC',dateStyle:'short',timeStyle:'short'}) + ' UTC' : '—';
    byId('region-source-issues').textContent = result.sourceProblems.length
      ? `${msg.regionSourceIssues}: ${result.sourceProblems.join(', ')}` : '';

    const chart = byId('region-chart'); chart.replaceChildren();
    const max = Math.max(1,...result.bins.map(b=>b.count));
    const description = result.bins.map(b =>
      `${b.fromHoursAgo}–${b.toHoursAgo} ${msg.regionRecent}: ${missing ? '—' : b.count}`).join('; ');
    chart.setAttribute('aria-label',`${msg.regionHistory}: ${description}`);
    for (const bucket of result.bins) {
      const col = document.createElement('div'); col.className = 'region-chart-col';
      const number = document.createElement('span'); number.className = 'region-chart-number';
      number.textContent = missing ? '—' : String(bucket.count);
      const barWrap = document.createElement('div'); barWrap.className = 'region-chart-track';
      const bar = document.createElement('span'); bar.className = 'region-chart-bar';
      bar.style.height = missing ? '0%' : `${100*bucket.count/max}%`;
      barWrap.append(bar);
      const label = document.createElement('span'); label.className = 'region-chart-label';
      label.textContent = `${bucket.fromHoursAgo}–${bucket.toHoursAgo}h`;
      col.append(number,barWrap,label); chart.append(col);
    }

    const sensors = byId('region-sensors'); sensors.replaceChildren();
    for (const sensor of result.sensors) {
      const li = document.createElement('li');
      const key = document.createElement('span'); key.textContent = sensor.key;
      const count = document.createElement('strong');
      count.textContent = sensor.memberships.toLocaleString(state.lang);
      li.append(key,count); sensors.append(li);
    }

    const leads = byId('region-leads'); leads.replaceChildren();
    for (const lead of result.leads) {
      const li = document.createElement('li');
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = `${lead.latitude.toFixed(3)}°, ${lead.longitude.toFixed(3)}° · ` +
        msg.regionRepeatedHours.replace('{hours}',String(lead.observedHours));
      button.disabled = !lead.eventId;
      button.addEventListener('click',() => {
        map.easeTo({center:[lead.longitude,lead.latitude],zoom:Math.max(map.getZoom(),8)});
        showRecord('candidate',lead.eventId);
      });
      li.append(button); leads.append(li);
    }
    byId('region-empty').hidden = missing || result.candidateCellHours > 0;
  }

  picker.addEventListener('click',() => {picking = !picking;draw();});
  byId('region-center').addEventListener('click',() => {
    const center = map.getCenter(); setRegion(center.lat,center.lng);
  });
  byId('region-clear').addEventListener('click',() => {
    state.regionLat = null; state.regionLon = null;
    picking = false; saveState(); draw();
  });
  byId('region-radius').addEventListener('change',event => {
    const radius = Number(event.target.value);
    if (![25,50,100,250].includes(radius)) return;
    state.radiusKm = radius;saveState();draw();
  });
  return {draw,handleMapClick,isPicking:()=>picking};
}
