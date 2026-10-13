// Two equal-radius geodesic circles, identical UTC observation windows.
// Pure descriptive research; no wildfire frequency, fire absence, or relative risk inference.
import {analyzeRegion,distanceKm,validRegion} from './region-explorer.mjs';
import {regionCoverageAudit} from './coverage-audit.mjs';

const SATELLITE = name => name === 'all' ||
  (typeof name === 'string' && name.startsWith('VIIRS_'));

export function compareRegions(snapshot,first,second,{
  hours=24,source='all',now=new Date()
}={}) {
  if(!validRegion(first)||!validRegion(second)||
      first.radiusKm!==second.radiusKm||![6,24,72].includes(hours)||
      !Number.isFinite(now.getTime())) {
    throw new RangeError('Two valid equal-radius regions and a 6/24/72-hour UTC window required');
  }
  const a=analyzeRegion(snapshot,first,hours,source,now);
  const b=analyzeRegion(snapshot,second,hours,source,now);
  const auditA=regionCoverageAudit(snapshot,first,{hours,now});
  const auditB=regionCoverageAudit(snapshot,second,{hours,now});
  const separationKm=distanceKm(first.latitude,first.longitude,
                                second.latitude,second.longitude);
  const overlaps=separationKm<first.radiusKm+second.radiusKm;
  const matchingSatelliteFilter=SATELLITE(source);
  const dataUsable=a.available&&b.available&&matchingSatelliteFilter;
  const limitations=[
    'Satellite cell-hours are thermal candidates, not confirmed wildfire occurrence, risk, area, spread, or severity.',
    'One global snapshot and equal-radius windows do not establish equally complete satellite observation opportunities.',
    'Land fraction, satellite overpass frequency, weather, fuel, source latency and agency coverage can differ by region.',
    'No absence of observed candidates proves the absence of wildfire.'
  ];
  if(overlaps)limitations.push('The two circles overlap and may count the same original observation.');
  if(!matchingSatelliteFilter)
    limitations.push('The source filter excludes satellite data; switch to all or a VIIRS source.');
  if(auditA.snapshotTruncated||auditB.snapshotTruncated)
    limitations.push('The public snapshot is truncated; relative thermal counts may be missing.');
  if(a.quality!=='current'||b.quality!=='current')
    limitations.push('One or both source views are stale, partial, or unavailable.');
  const sensorKeys=new Set([...a.sensors.map(x=>x.key),...b.sensors.map(x=>x.key)]);
  const memberships=new Map(a.sensors.map(x=>[x.key,x.memberships]));
  const other=new Map(b.sensors.map(x=>[x.key,x.memberships]));
  return {
    schemaVersion:1,status:!matchingSatelliteFilter?'unsupported_source_filter':
      !a.available||!b.available?'unavailable':
      overlaps?'overlapping_areas':
      a.quality!=='current'||b.quality!=='current'||
      auditA.snapshotTruncated||auditB.snapshotTruncated?'incomplete_source_evidence':
      'descriptive_thermal_comparison_only',
    createdAt:now.toISOString(),
    hours,source,unit:'distinct_0_05_degree_cell_hours_not_fire_count',
    sameObservationWindow:true,sameRadiusKm:first.radiusKm,
    centerSeparationKm:Number(separationKm.toFixed(3)),
    areasOverlap:overlaps,
    first:{...first,quality:a.quality,available:a.available,
      candidateCellHours:dataUsable?a.candidateCellHours:null,
      distinctCells:dataUsable?a.distinctCells:null,
      recurringCells:dataUsable?a.recurringCells:null,
      latestObservedAt:dataUsable?a.latestObservedAt:null,
      scanAt:a.scanAt},
    second:{...second,quality:b.quality,available:b.available,
      candidateCellHours:dataUsable?b.candidateCellHours:null,
      distinctCells:dataUsable?b.distinctCells:null,
      recurringCells:dataUsable?b.recurringCells:null,
      latestObservedAt:dataUsable?b.latestObservedAt:null,
      scanAt:b.scanAt},
    differenceCellHours:dataUsable?a.candidateCellHours-b.candidateCellHours:null,
    sensorMemberships:[...sensorKeys].sort().map(key=>({
      key,first:memberships.get(key)||0,second:other.get(key)||0
    })),
    sourceEvidence:{first:auditA,second:auditB},
    independentlyVerifiedFireDifference:null,
    fireAbsenceInEitherRegionVerified:false,
    wildfireRiskRankingAvailable:false,
    comparableAcquisitionCoverageVerified:false,
    descriptiveComparisonNotIndependentlyValidated:true,
    limitations
  };
}
