// Global provider coverage evidence, not a fire-risk score or completeness claim.
// A complete upstream request never proves that its observations cover a region.
import {distanceKm,validRegion} from './region-explorer.mjs';

export const COVERAGE_SOURCES = Object.freeze([
  {key:'VIIRS_NOAA20_NRT',kind:'satellite',scope:'world_request',
   url:'https://firms.modaps.eosdis.nasa.gov/',license:'https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy'},
  {key:'VIIRS_NOAA21_NRT',kind:'satellite',scope:'world_request',
   url:'https://firms.modaps.eosdis.nasa.gov/',license:'https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy'},
  {key:'nifc_wfigs',kind:'agency',scope:'us_agency',
   url:'https://www.nifc.gov/fire-information/maps',license:'https://www.nifc.gov/fire-information/maps'},
  {key:'cwfis',kind:'agency',scope:'canada_agency',
   url:'https://cwfis.cfs.nrcan.gc.ca/en/',license:'https://cwfis.cfs.nrcan.gc.ca/en/'},
  {key:'nws_grid',kind:'weather',scope:'us_on_demand',
   url:'https://www.weather.gov/documentation/services-web-api',license:'https://www.weather.gov/documentation/services-web-api'},
  {key:'nifc_perimeter',kind:'perimeter',scope:'us_on_demand',
   url:'https://www.nifc.gov/fire-information/maps',license:'https://www.nifc.gov/fire-information/maps'}
]);

const SCAN_STALE_MS=90*60_000;
const KNOWABLE_STATUS=new Set(['complete','failed','deferred','partial']);
const validPoint=(lat,lon)=>typeof lat==='number'&&typeof lon==='number'&&
  Number.isFinite(lat)&&Number.isFinite(lon)&&lat>=-90&&lat<=90&&lon>=-180&&lon<=180;
const within=(record,region)=>validPoint(record?.latitude,record?.longitude)&&
  distanceKm(region.latitude,region.longitude,record.latitude,record.longitude)<=region.radiusKm;
const timeValue=value=>typeof value==='string'&&value.trim()?Date.parse(value):NaN;

export function regionCoverageAudit(snapshot,region,{hours=72,now=new Date()}={}) {
  if(!validRegion(region)||![6,24,72].includes(hours))
    throw new RangeError('Valid region and 6/24/72-hour window required');
  const asOf=now.getTime();
  if(!Number.isFinite(asOf))throw new RangeError('Valid evaluation time required');
  const scan=timeValue(snapshot?.manifest?.last_scan_at);
  const snapshotAvailable=Number.isFinite(scan)&&scan<=asOf+60_000;
  const snapshotStale=!snapshotAvailable||asOf-scan>SCAN_STALE_MS;
  const partial=snapshot?.manifest?.data_status==='partial';
  const truncated=snapshot?.manifest?.truncated===true;
  const start=asOf-hours*3_600_000;
  const sourceMap=new Map();
  for(const source of snapshot?.sources||[]) {
    if(source&&typeof source.key==='string'&&!sourceMap.has(source.key))
      sourceMap.set(source.key,source);
  }

  const candidates=new Map();
  const candidateLatest=new Map();
  const incidents=new Map();
  const incidentLatest=new Map();
  if(snapshotAvailable) {
    for(const e of snapshot?.events||[]) {
      const observed=timeValue(e?.observed_at);
      // A source's future acquisition is not usable at this decision time.
      const received=timeValue(e?.received_at);
      if(!within(e,region)||!Number.isFinite(observed)||observed<start||
         observed>Math.min(asOf,scan)||
         (Number.isFinite(received)&&received>Math.min(asOf,scan)))continue;
      const hour=Math.floor(observed/3_600_000);
      for(const name of new Set(Array.isArray(e.sources)?e.sources:[])) {
        if(typeof name!=='string'||!name.startsWith('VIIRS_'))continue;
        if(!candidates.has(name))candidates.set(name,new Set());
        // These are already 0.05-degree cell-hour candidates in public snapshot.
        candidates.get(name).add(e.event_id||`${e.latitude},${e.longitude},${hour}`);
        candidateLatest.set(name,Math.max(candidateLatest.get(name)||0,observed));
      }
    }
    for(const e of snapshot?.incidents||[]) {
      if(!within(e,region)||!['nifc_wfigs','cwfis'].includes(e.provider))continue;
      // Current provider layers are not bounded to the satellite hours window.
      // Source timestamps may be absent; reject future-dated source revisions.
      const changed=timeValue(e.modified_at||e.last_seen_at);
      if(Number.isFinite(changed)&&changed>Math.min(asOf,scan))continue;
      if(!incidents.has(e.provider))incidents.set(e.provider,new Set());
      incidents.get(e.provider).add(e.official_id||`${e.latitude},${e.longitude}`);
      if(Number.isFinite(changed))
        incidentLatest.set(e.provider,Math.max(incidentLatest.get(e.provider)||0,changed));
    }
  }

  const rows=COVERAGE_SOURCES.map(source=>{
    const observation=sourceMap.get(source.key);
    const collected=source.kind==='satellite'||source.kind==='agency';
    let status='not_in_snapshot';
    if(collected) {
      if(!snapshotAvailable)status='snapshot_unavailable';
      else if(!observation)status='unreported';
      else if(!KNOWABLE_STATUS.has(observation.status))status='unreported';
      else if(observation.status!=='complete')status=observation.status;
      else if(snapshotStale)status='stale_snapshot';
      else if(partial||truncated)status='snapshot_partial';
      else status='complete_request';
    } else status='not_a_snapshot_source';

    const byKind=source.kind==='satellite'?candidates:
      source.kind==='agency'?incidents:null;
    const observed=byKind?.get(source.key).size??0;
    const count=collected&&snapshotAvailable?observed:null;
    const latest=source.kind==='satellite'?candidateLatest.get(source.key):
      source.kind==='agency'?incidentLatest.get(source.key):null;
    const productAge=observation?.product_age_seconds;
    const ageSec=typeof productAge==='number'&&Number.isFinite(productAge)&&
      productAge>=0?productAge:null;
    const failureCount=observation?.consecutive_failures;
    return {
      ...source,
      status,recordedSourceState:observation?.status||null,
      observedInCircle:count,
      observedUnit:source.kind==='satellite'?'candidate_cell_hours':
        source.kind==='agency'?'current_agency_layer_ids':'not_measured',
      latestObservedAt:Number.isFinite(latest)?new Date(latest).toISOString():null,
      productAgeSeconds:ageSec,
      consecutiveFailures:Number.isInteger(failureCount)&&failureCount>=0?failureCount:null,
      sourceReportedAt:observation?.last_success_at||null,
      capabilityOnly:!collected,
      regionCoverageVerified:false,
    };
  });
  return {
    schemaVersion:1,createdAt:new Date(asOf).toISOString(),
    lastScanAt:snapshotAvailable?new Date(scan).toISOString():null,
    snapshotState:!snapshotAvailable?'unavailable':snapshotStale?'stale':
      partial||truncated?'partial':'current',
    snapshotTruncated:truncated,
    region:{latitude:region.latitude,longitude:region.longitude,radiusKm:region.radiusKm,
      geometry:'geodesic_circle_not_country_boundary'},
    satelliteWindowHours:hours,
    rows,regionCoverageVerified:false,
    confirmedFireCoverageVerified:false,
    validNonFireLabelsAvailable:false,
    notes:[
      'A completed world FIRMS API request is not proof of complete satellite coverage, acquisition or detection.',
      'Official NIFC and CWFIS sources report only provider-defined current layers; no country polygon boundary was inferred.',
      'Weather and perimeter feeds are on-demand and their availability is not monitored by this snapshot.',
      'Zero reported records, absent sources, outages and stale data never establish wildfire absence.',
      'Thermal candidates are not independently verified wildfire incidents, forecasts, or outcome labels.'
    ]
  };
}
