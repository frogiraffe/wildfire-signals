import {validateAnnualArchive,selectAnnualArchive} from './analytics-data.mjs';
import {validateSpatialRecurrence,selectSpatialRecurrence} from './analytics-data.mjs';
import {historicalAudit} from './historical-audit.mjs';
import {investigationManifest} from './investigation-manifest.mjs';

export function buildResearchReport(annual,spatial,{study,sensor,from,to,metric,gridFilter}) {
  const manifest=investigationManifest({study,sensor,from,to,metric,gridFilter});
  validateAnnualArchive(annual);
  validateSpatialRecurrence(spatial);
  if(annual.region.region_id!==study)throw new Error('Archive study mismatch');
  const {months}=selectAnnualArchive(annual,{from,to,provider:sensor,variable:'temperature_c'});
  const region=selectSpatialRecurrence(spatial,study);
  const audit=historicalAudit(spatial,study);
  const rawPixels=months.reduce((sum,row)=>sum+row.rawPixels,0);
  const candidateCellHours=months.reduce((sum,row)=>sum+row.candidateCellHours,0);
  return {schema_version:1,kind:'source_backed_historical_research_report',selection:manifest,
    annual:{study,monthsWithArchivedCandidates:months.length,rawPixels,candidateCellHours,
      evidenceSha256:annual.evidence_sha256,sourcePeriod:[annual.start_date,annual.end_date]},
    geography:{publishedBins:audit.publishedBins,mappedPixels:audit.mappedPixels,
      unpublishedPixels:audit.unmappedPixels,studyTotalPixels:audit.totalPixels,
      evidenceSha256:spatial.evidence_sha256,
      independentlyClassified:false,gridPeriod:'2023–2025 (not filtered by selected months)'},
    quality:{satelliteAcquisitionExposureVerified:false,independentWildfireOutcomesVerified:false,
      validatedFireRiskAvailable:false,verifiedNoFireMonths:false,
      note:'Archived thermal detections, not confirmed fires, burn perimeters or fire incidence. Missing archive rows do not establish no fire.'}};
}
export function formatResearchReport(report) {
  const a=report.annual,g=report.geography,q=report.quality;
  return ['# Wildfire Signals — Historical research evidence',
    'Study: '+a.study,'Archive selection: '+report.selection.annual_month_window_utc.from+
      ' to '+report.selection.annual_month_window_utc.to,
    'Sensor: '+report.selection.sensor,
    'Archived candidate pixels: '+a.rawPixels,
    'Candidate cell-hours: '+a.candidateCellHours,
    'UTC months with archived candidates: '+a.monthsWithArchivedCandidates,
    'Published research bins (full 2023–2025 period): '+g.publishedBins,
    'Pixels represented in published bins: '+g.mappedPixels,
    'Pixels outside published bins: '+g.unpublishedPixels,
    'Annual evidence SHA-256: '+a.evidenceSha256,
    'Spatial evidence SHA-256: '+g.evidenceSha256,
    'Uncertainty: '+q.note,
    'Satellite opportunity verified: No',
    'Independent wildfire outcomes verified: No',
    'Spatial bins are not restricted to the annual month selection.'
  ].join('\n');
}
