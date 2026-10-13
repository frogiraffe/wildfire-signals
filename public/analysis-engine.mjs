// First statistical analysis slice for worldwide, current NASA FIRMS snapshot observations.
// All results are DESCRIPTIVE: a thermal cell-hour is not a verified wildfire.
import {distanceKm,normalLongitude,validRegion} from './region-explorer.mjs';
import {regionCoverageAudit} from './coverage-audit.mjs';

const SENSOR_KEYS=['VIIRS_NOAA20_NRT','VIIRS_NOAA21_NRT'];
const HOUR=3_600_000;
const finiteTime=value=>typeof value==='string'&&value.trim()?Date.parse(value):NaN;
const median=arr=>{
  if(!arr.length)return null;
  const sorted=[...arr].sort((a,b)=>a-b),i=Math.floor(sorted.length/2);
  return sorted.length%2?sorted[i]:(sorted[i-1]+sorted[i])/2;
};
const iso=ms=>new Date(ms).toISOString();
const validSource=s=>s==='all'||SENSOR_KEYS.includes(s);

// This function does not estimate overpass opportunities, wildfire occurrence,
// precipitation effects, probability, area, intensity, or hypothesis significance.
export function analyzeRegionalSignals(snapshot,region,{
  hours=24,source='all',now=new Date()
}={}) {
  if(!validRegion(region)||![6,24,72].includes(hours)||
     !validSource(source)||!(now instanceof Date)||!Number.isFinite(now.getTime()))
    throw new RangeError('Valid global region, 6/24/72-hour window, VIIRS source, and clock required');
  const end=now.getTime(),start=end-hours*HOUR;
  const scan=finiteTime(snapshot?.manifest?.last_scan_at);
  const usable=Number.isFinite(scan)&&scan<=end+60_000;
  const cutoff=Math.min(end,scan);
  const scope=source==='all'?[...SENSOR_KEYS]:[source];
  const statusMap=new Map();
  for(const row of snapshot?.sources||[]) {
    if(row&&typeof row.key==='string'&&!statusMap.has(row.key))
      statusMap.set(row.key,row.status);
  }
  const sourceState=scope.map(key=>({key,status:statusMap.get(key)||'unreported'}));
  const failing=sourceState.filter(row=>row.status!=='complete').map(row=>row.key);
  const truncated=snapshot?.manifest?.truncated===true;
  const partiallyReported=snapshot?.manifest?.data_status==='partial';
  const stale=usable&&end-scan>90*60_000;
  const quality=!usable?'unavailable':stale?'stale':
    failing.length||partiallyReported||truncated?'incomplete':'current';
  const limitations=[
    'A 0.05-degree UTC cell-hour is a satellite thermal candidate, not an independently verified wildfire.',
    'NASA FIRMS satellite acquisition opportunities, cloud/smoke obstruction, observation latency and land exposure are not measured in this snapshot.',
    'Counts, recurrence, source co-membership, and an apparent temporal slope are NOT wildfire incidence, severity, burned area, spread speed, risk or forecast performance.',
    'A zero thermal cell-hour count cannot confirm the absence of wildfire.'
  ];
  if(!usable)limitations.push('No usable as-of collection scan. All quantitative statistics are unavailable.');
  if(stale)limitations.push('Source scan is stale relative to analysis time; observations may be missing.');
  if(truncated)limitations.push('The snapshot was truncated; observed statistics are a lower-bound subset.');
  if(failing.length)limitations.push('Incomplete source states: '+failing.join(', '));
  if(partiallyReported)limitations.push('The collection manifest reports partial source data.');
  const provenance=regionCoverageAudit(snapshot,region,{hours,now});
  const metrics={
    cellHours:null,distinctCells:null,recurrentCells:null,
    recurrentCellHours:null,consecutiveHourTransitions:null,
    multiSensorCellHours:null,multiSensorPercent:null,
    lastObservedAt:null,medianBinCellHours:null,madBinCellHours:null,
    laterMinusEarlier:null,laterToEarlierRatio:null,
    theilSenCellHoursPerHour:null,trendDirection:'unavailable'
  };
  const bucketHours=hours/6;
  const bins=Array.from({length:6},(_,i)=>({
    startAt:iso(start+i*bucketHours*HOUR),
    endAt:iso(start+(i+1)*bucketHours*HOUR),
    cellHours:null,distinctCells:null,sensorCellHours:null
  }));
  const result={
    schemaVersion:1,kind:'global_regional_satellite_signal_statistics',
    researchMaturity:'descriptive_observational_not_validated_wildfire_model',
    asOf:iso(end),lastScanAt:usable?iso(scan):null,
    window:{startAt:iso(start),endAt:iso(end),hours,bucketHours,
      boundary:'start_inclusive_end_inclusive'},
    region:{...region,geometry:'geodesic_circle_wgs84'},
    sourceFilter:source,selectedSensors:scope,sourceStates:sourceState,
    status:quality,analysisAvailable:usable,coverageVerified:false,
    satelliteOverpassDenominatorAvailable:false,
    verifiedWildfireCount:null,verifiedNonfireCount:null,
    wildfireProbability:null,spreadForecast:null,
    observedFireSizeKm2:null,hypothesisPValue:null,
    metrics,bins,sensorSeries:[],sensorCoMembership:[],
    sourceCoverage:provenance,limitations
  };
  if(!usable)return result;

  const cells=new Map();
  // Dedupe by ORIGINAL 0.05-degree UTC cell-hour. A later scan can repeat
  // the same source observation without adding any new empirical evidence.
  for(const event of snapshot?.events||[]) {
    if(event?.kind!==undefined&&event.kind!=='satellite_candidate')continue;
    const t=finiteTime(event?.observed_at);
    const received=finiteTime(event?.received_at);
    if(!Number.isFinite(t)||t<start||t>cutoff||
       (Number.isFinite(received)&&received>cutoff)||
       !Number.isFinite(event.latitude)||!Number.isFinite(event.longitude)||
       event.latitude < -90||event.latitude >90||
       event.longitude< -180||event.longitude>180||
       distanceKm(region.latitude,region.longitude,event.latitude,event.longitude)>region.radiusKm)
      continue;
    const sensors=[...new Set(Array.isArray(event.sources)?event.sources:[])]
      .filter(s=>scope.includes(s));
    if(!sensors.length)continue;
    const lat=Math.floor(event.latitude*20);
    const lon=Math.floor(normalLongitude(event.longitude)*20);
    // Longitude 180 is normalized to -180 on both sides of the date line.
    const hour=Math.floor(t/HOUR);
    const key=lat+','+lon+','+hour;
    if(!cells.has(key))cells.set(key,{
      lat,lon,hour,t,cellKey:lat+','+lon,sensors:new Set()
    });
    const cell=cells.get(key);
    cell.t=Math.max(t,cell.t);
    for(const s of sensors)cell.sensors.add(s);
  }
  const rows=[...cells.values()].sort((a,b)=>a.hour-b.hour||
    a.lat-b.lat||a.lon-b.lon);
  const distinct=new Map();
  const sensorKeys=scope.map(key=>({key,bins:Array(6).fill(0),
    cellHours:0,distinctCells:new Set(),latest:-Infinity}));
  const sensorIndex=new Map(sensorKeys.map(x=>[x.key,x]));
  const co=new Map();
  for(const row of rows){
    const idx=Math.max(0,Math.min(5,Math.floor((row.t-start)/(bucketHours*HOUR))));
    const bin=bins[idx];
    bin.cellHours=(bin.cellHours||0)+1;
    if(!bin._locations)bin._locations=new Set();
    bin._locations.add(row.cellKey);
    if(!bin._sensorCounts)bin._sensorCounts=new Map();
    const hoursAtCell=distinct.get(row.cellKey)||new Set();
    hoursAtCell.add(row.hour);
    distinct.set(row.cellKey,hoursAtCell);
    for(const key of row.sensors) {
      const series=sensorIndex.get(key);
      series.cellHours++;
      series.bins[idx]++;
      series.distinctCells.add(row.cellKey);
      series.latest=Math.max(series.latest,row.t);
      bin._sensorCounts.set(key,(bin._sensorCounts.get(key)||0)+1);
    }
    if(row.sensors.size>1) {
      const key=[...row.sensors].sort().join(' + ');
      co.set(key,(co.get(key)||0)+1);
    }
  }
  for(const b of bins) {
    b.cellHours=b.cellHours||0;
    b.distinctCells=b._locations?.size||0;
    b.sensorCellHours=Object.fromEntries(scope.map(key=>[key,b._sensorCounts?.get(key)||0]));
    delete b._locations;delete b._sensorCounts;
  }
  const counts=bins.map(b=>b.cellHours);
  const med=median(counts);
  const slopes=[];
  for(let i=0;i<6;i++)for(let j=i+1;j<6;j++)
    slopes.push((counts[j]-counts[i])/((j-i)*bucketHours));
  const slope=median(slopes);
  const earlier=counts.slice(0,3).reduce((a,b)=>a+b,0);
  const later=counts.slice(3).reduce((a,b)=>a+b,0);
  const recurring=[...distinct.values()].filter(x=>x.size>=2);
  const consecutive= [...distinct.values()].reduce((total,set)=>{
    let transitions=0;
    for(const h of set)if(set.has(h-1))transitions++;
    return total+transitions;
  },0);
  const last=rows.length?Math.max(...rows.map(row=>row.t)):null;
  Object.assign(metrics,{
    cellHours:rows.length,distinctCells:distinct.size,
    recurrentCells:recurring.length,
    recurrentCellHours:recurring.reduce((total,set)=>total+set.size,0),
    consecutiveHourTransitions:consecutive,
    multiSensorCellHours:[...co.values()].reduce((a,b)=>a+b,0),
    multiSensorPercent:rows.length?
      Number((100*[...co.values()].reduce((a,b)=>a+b,0)/rows.length).toFixed(1)):null,
    lastObservedAt:last===null?null:iso(last),
    medianBinCellHours:med,madBinCellHours:median(counts.map(c=>Math.abs(c-med))),
    laterMinusEarlier:later-earlier,laterToEarlierRatio:earlier>0?
      Number((later/earlier).toFixed(3)):null,
    theilSenCellHoursPerHour:Number(slope.toFixed(4)),
    trendDirection:slope>0?'upward_descriptive':slope<0?'downward_descriptive':'flat_descriptive'
  });
  result.sensorSeries=sensorKeys.map(s=>({
    key:s.key,sourceStatus:statusMap.get(s.key)||'unreported',
    cellHours:s.cellHours,distinctCells:s.distinctCells.size,
    latestObservedAt:Number.isFinite(s.latest)?iso(s.latest):null,
    bins:s.bins
  }));
  result.sensorCoMembership=[...co.entries()].sort(([a],[b])=>a.localeCompare(b))
    .map(([key,cellHours])=>({sensors:key.split(' + '),cellHours,
      independentWildfireConfirmation:false}));
  return result;
}
