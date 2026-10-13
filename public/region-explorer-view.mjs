import {analyzeRegion,circleBoundary,normalLongitude,validRegion} from './region-explorer.mjs';
import {regionCoverageAudit} from './coverage-audit.mjs';
import {compareRegions} from './region-compare.mjs';
import {analyzeRegionalSignals} from './analysis-engine.mjs';

// UI controller only; all statistical and geographic calculations remain pure and testable.
export function createRegionExplorer({map,state,getSnapshot,saveState,showRecord,messages}) {
  const byId = id => document.getElementById(id);
  let picking = null;
  let lastCoverage = null;
  let lastComparison = null;
  let lastAnalysis = null;
  const picker = byId('region-pick');

  function drawCoverage(audit,msg) {
    const statuses = {
      complete_request:msg.coverageCompleteRequest,failed:msg.coverageFailed,
      deferred:msg.coverageDeferred,partial:msg.coveragePartial,
      unreported:msg.coverageUnreported,snapshot_partial:msg.coverageSnapshotPartial,
      stale_snapshot:msg.coverageStaleSnapshot,
      snapshot_unavailable:msg.coverageSnapshotUnavailable,
      not_a_snapshot_source:msg.coverageNotMonitored
    };
    const scopeText = {
      world_request:msg.coverageScopeWorld,us_agency:msg.coverageScopeUS,
      canada_agency:msg.coverageScopeCA,us_on_demand:msg.coverageScopeOnDemand
    };
    const kinds = {
      satellite:msg.coverageKindSatellite,agency:msg.coverageKindAgency,
      weather:msg.coverageKindWeather,perimeter:msg.coverageKindPerimeter
    };
    const snapshotStates={
      unavailable:msg.coverageStatusUnavailable,stale:msg.coverageStatusStale,
      partial:msg.coverageStatusPartial,current:msg.coverageStatusCurrent
    };
    byId('coverage-snapshot-status').textContent =
      `${snapshotStates[audit.snapshotState]} · ${msg.coverageDisclaimer}`;
    const list=byId('coverage-source-list');list.replaceChildren();
    for (const source of audit.rows) {
      const li=document.createElement('li');
      const title=document.createElement('strong');title.textContent=source.key;
      const meta=document.createElement('span');meta.textContent =
        `${kinds[source.kind]} · ${scopeText[source.scope]}`;
      const status=document.createElement('span');status.className='coverage-source-status';
      status.textContent=statuses[source.status]||msg.coverageUnreported;
      const count=document.createElement('span');count.className='coverage-source-count';
      count.textContent=`${msg.coverageObserved}: ${source.observedInCircle===null
        ? msg.coverageNotMeasured : source.observedInCircle===0
          ? msg.coverageNoRecords : source.observedInCircle.toLocaleString(state.lang)}`;
      const details=document.createElement('small');
      const age=source.productAgeSeconds===null?'—':
        `${Math.round(source.productAgeSeconds/60)} min`;
      details.textContent=`${msg.coverageAge}: ${age} · ${msg.coverageFailures}: ` +
        `${source.consecutiveFailures??'—'}`;
      const links=document.createElement('span');
      links.className='coverage-source-links';
      const reference=document.createElement('a');reference.href=source.url;
      reference.textContent=msg.coverageProvenance;reference.target='_blank';
      reference.rel='noopener noreferrer';
      links.append(reference);
      li.append(title,meta,status,count,details,links);
      list.append(li);
    }
  }


  function drawStatistics(report,msg) {
    const quality={
      current:msg.statsQualityCurrent,incomplete:msg.statsQualityPartial,
      stale:msg.statsQualityStale,unavailable:msg.statsQualityUnavailable
    };
    byId('analysis-engine-quality').textContent=
      report ? quality[report.status] : msg.statsQualityUnsupported;
    const stats=report?.metrics||{};
    const fmt=value=>value===null||value===undefined?'—':
      typeof value==='number'?value.toLocaleString(state.lang,{maximumFractionDigits:4}):
        String(value);
    for(const [id,value] of [
      ['stats-median',stats.medianBinCellHours],
      ['stats-mad',stats.madBinCellHours],
      ['stats-slope',stats.theilSenCellHoursPerHour],
      ['stats-change',stats.laterMinusEarlier],
      ['stats-transitions',stats.consecutiveHourTransitions],
      ['stats-coobs',stats.multiSensorCellHours]
    ])byId(id).textContent=fmt(value);
    const body=byId('stats-timeline-body');body.replaceChildren();
    const locale=state.lang==='tr'?'tr-TR':'en-US';
    for(const bin of report?.bins||[]) {
      const tr=document.createElement('tr');
      const from=new Date(bin.startAt).toLocaleString(locale,{timeZone:'UTC',
        month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
      const to=new Date(bin.endAt).toLocaleString(locale,{timeZone:'UTC',
        month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false});
      for(const item of [from+' – '+to+' UTC',fmt(bin.cellHours),
        fmt(bin.distinctCells),bin.sensorCellHours===null?'—':
          Object.entries(bin.sensorCellHours).map(([key,value])=>
            key.replace('VIIRS_','')+': '+value).join(' / ')]) {
        const td=document.createElement('td');
        td.textContent=item;tr.append(td);
      }
      body.append(tr);
    }
    const sensors=byId('stats-sensors');sensors.replaceChildren();
    for(const row of report?.sensorSeries||[]) {
      const li=document.createElement('li');
      const label=document.createElement('span');
      label.textContent=row.key+' · '+row.sourceStatus;
      const count=document.createElement('strong');
      count.textContent=fmt(row.cellHours);
      li.append(label,count);sensors.append(li);
    }
    byId('stats-download').disabled=!report;
  }

  function currentRegion() {
    const region = {latitude:state.regionLat,longitude:state.regionLon,
      radiusKm:state.radiusKm};
    return Number.isFinite(state.regionLat) && Number.isFinite(state.regionLon) &&
      validRegion(region) ? region : null;
  }

  function comparisonRegion() {
    if (!currentRegion() || !Number.isFinite(state.compareLat) ||
        !Number.isFinite(state.compareLon)) return null;
    const region={latitude:state.compareLat,longitude:state.compareLon,
      radiusKm:state.radiusKm};
    return validRegion(region)?region:null;
  }

  function setRegion(latitude,longitude,target='primary') {
    const lat=Number(Math.max(-90,Math.min(90,latitude)).toFixed(5));
    const lon=Number(normalLongitude(longitude).toFixed(5));
    if(target==='comparison' && currentRegion()) {
      state.compareLat=lat;state.compareLon=lon;
    } else {
      state.regionLat=lat;state.regionLon=lon;
    }
    picking=null;
    saveState();
    draw();
  }

  function handleMapClick(event) {
    if (!picking) return;
    setRegion(event.lngLat.lat,event.lngLat.lng,picking);
  }

  function draw() {
    const msg = messages[state.lang];
    const region = currentRegion();
    picker.textContent = picking==='primary' ? msg.regionCancel : msg.regionPick;
    picker.setAttribute('aria-pressed',String(picking==='primary'));
    byId('compare-pick').textContent = picking==='comparison'
      ? msg.regionCancel : msg.comparePick;
    byId('compare-pick').setAttribute('aria-pressed',String(picking==='comparison'));
    byId('compare-pick').disabled = !region;
    byId('compare-center').disabled = !region;
    map.getCanvas().classList.toggle('region-pick-mode',Boolean(picking));
    byId('region-radius').value = String(state.radiusKm);
    byId('region-results').hidden = !region;
    lastCoverage = null;
    lastComparison = null;
    lastAnalysis = null;
    byId('region-clear').disabled = !region;
    byId('region-location').textContent = region
      ? `${region.latitude.toFixed(4)}°, ${region.longitude.toFixed(4)}° · ${region.radiusKm} km`
      : msg.regionNoSelection;
    const outline = map.getSource('selected-region');
    if (outline) outline.setData(region ? circleBoundary(region) :
      {type:'FeatureCollection',features:[]});
    const comparison = comparisonRegion();
    byId('compare-results').hidden = !comparison;
    byId('compare-clear').disabled = !comparison;
    byId('compare-location').textContent = comparison
      ? `${comparison.latitude.toFixed(4)}°, ${comparison.longitude.toFixed(4)}° · ${comparison.radiusKm} km`
      : msg.compareNoSelection;
    const secondOutline=map.getSource('comparison-region');
    if(secondOutline)secondOutline.setData(comparison?circleBoundary(comparison):
      {type:'FeatureCollection',features:[]});
    if (!region) return;

    const now=new Date();
    const result = analyzeRegion(getSnapshot(),region,state.hours,state.source,now);
    lastCoverage=regionCoverageAudit(getSnapshot(),region,{hours:state.hours,now});
    drawCoverage(lastCoverage,msg);
    lastAnalysis=state.source==='all'||state.source.startsWith('VIIRS_')
      ? analyzeRegionalSignals(getSnapshot(),region,{hours:state.hours,source:state.source,now})
      : null;
    drawStatistics(lastAnalysis,msg);
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
    if(comparison) {
      const pair=compareRegions(getSnapshot(),region,comparison,
        {hours:state.hours,source:state.source});
      lastComparison=pair;
      const first=pair.first.candidateCellHours;
      const second=pair.second.candidateCellHours;
      const fmt=x=>x===null?'—':x.toLocaleString(state.lang);
      byId('compare-a-count').textContent=fmt(first);
      byId('compare-b-count').textContent=fmt(second);
      byId('compare-diff').textContent=pair.differenceCellHours===null?'—':
        (pair.differenceCellHours>0?'+':'')+fmt(pair.differenceCellHours);
      byId('compare-separation').textContent=
        pair.centerSeparationKm.toLocaleString(state.lang)+' km';
      const notices=[];
      const status={
        unsupported_source_filter:msg.compareUnsupported,
        unavailable:msg.compareNoSnapshot,
        overlapping_areas:msg.compareOverlap,
        incomplete_source_evidence:msg.comparePartial,
        descriptive_thermal_comparison_only:msg.compareCurrent
      };
      notices.push(status[pair.status]);
      if(pair.areasOverlap && pair.status!=='overlapping_areas')
        notices.push(msg.compareOverlap);
      if((pair.first.quality!=='current'||pair.second.quality!=='current') &&
          pair.status!=='incomplete_source_evidence')notices.push(msg.comparePartial);
      byId('compare-quality').textContent=notices.join(' ');
      byId('compare-caveat').textContent=msg.compareCaveat;
      const sensors=byId('compare-sensors');sensors.replaceChildren();
      for(const sensor of pair.sensorMemberships) {
        const li=document.createElement('li');
        const label=document.createElement('span');label.textContent=sensor.key;
        const amount=document.createElement('strong');
        amount.textContent=`${fmt(sensor.first)} / ${fmt(sensor.second)}`;
        li.append(label,amount);sensors.append(li);
      }
    }
  }

  byId('stats-download').addEventListener('click',() => {
    if(!lastAnalysis)return;
    const data=new Blob([JSON.stringify(lastAnalysis,null,2)+'\n'],
      {type:'application/json'});
    const url=URL.createObjectURL(data);
    const link=document.createElement('a');
    link.href=url;link.download='wildfire-regional-statistical-analysis.json';
    document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  byId('coverage-download').addEventListener('click',() => {
    if(!lastCoverage)return;
    const report=new Blob([JSON.stringify(lastCoverage,null,2)+'\n'],
      {type:'application/json'});
    const url=URL.createObjectURL(report);
    const link=document.createElement('a');
    link.href=url;link.download='wildfire-region-coverage.json';
    document.body.append(link);
    link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  byId('compare-download').addEventListener('click',() => {
    if(!lastComparison)return;
    const data=new Blob([JSON.stringify(lastComparison,null,2)+'\n'],
      {type:'application/json'});
    const url=URL.createObjectURL(data);
    const link=document.createElement('a');
    link.href=url;link.download='wildfire-two-region-comparison.json';
    document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  picker.addEventListener('click',() => {
    picking=picking==='primary'?null:'primary';draw();
  });
  byId('compare-pick').addEventListener('click',() => {
    if(!currentRegion())return;
    picking=picking==='comparison'?null:'comparison';draw();
  });
  byId('compare-center').addEventListener('click',() => {
    if(!currentRegion())return;
    const center=map.getCenter();
    setRegion(center.lat,center.lng,'comparison');
  });
  byId('compare-clear').addEventListener('click',() => {
    state.compareLat=null;state.compareLon=null;
    picking=null;saveState();draw();
  });
  byId('region-center').addEventListener('click',() => {
    const center = map.getCenter(); setRegion(center.lat,center.lng);
  });
  byId('region-clear').addEventListener('click',() => {
    state.regionLat = null; state.regionLon = null;
    state.compareLat=null;state.compareLon=null;
    picking=null;saveState();draw();
  });
  byId('region-radius').addEventListener('change',event => {
    const radius = Number(event.target.value);
    if (![25,50,100,250].includes(radius)) return;
    state.radiusKm = radius;saveState();draw();
  });
  return {draw,handleMapClick,isPicking:()=>picking};
}
