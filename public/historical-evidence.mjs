// Retrospective evidence comparison. Counts are NOT fire incidence or risk.
import {selectAnnualArchive} from './analytics-data.mjs';

export function compareHistoricalEvidence(studies, selection) {
  if (!Array.isArray(studies) || studies.length === 0) throw new Error('No archive studies');
  const rows=studies.map(({pilot,report})=>{
    const {months}=selectAnnualArchive(report,selection);
    const rawPixels=months.reduce((n,r)=>n+r.rawPixels,0);
    const candidateCellHours=months.reduce((n,r)=>n+r.candidateCellHours,0);
    const weatherObservedMonths=months.filter(r=>r.stationMedian!==null).length;
    return {region:pilot.label,regionId:pilot.id,monthsWithCandidates:months.length,
      rawPixels,candidateCellHours,weatherObservedMonths,
      evidenceSha256:report.evidence_sha256,
      satelliteOpportunityVerified:false,independentFireOutcomesVerified:false};
  });
  return {schemaVersion:1,selection:{...selection},rows,
    interpretation:'Retrospective thermal detections only; selected regions lack comparable verified satellite exposure. Differences are not wildfire risk, rates, prevalence, or independently adjudicated fires.',
    wildfireRiskComparisonAvailable:false,rateRatio:null,fireProbability:null};
}

const quote=value=>{
  const raw=String(value??'');
  const safe=['=','+','-','@'].some(prefix=>raw.trimStart().startsWith(prefix)) ? "'"+raw : raw;
  return '"'+safe.replaceAll('"','""')+'"';
};
export function historicalEvidenceCsv(comparison) {
  const headers=['region','regionId','monthsWithCandidates','rawPixels','candidateCellHours',
    'weatherObservedMonths','evidenceSha256','satelliteOpportunityVerified','independentFireOutcomesVerified'];
  return '\uFEFF'+headers.map(quote).join(',')+'\r\n'+comparison.rows.map(row=>
    headers.map(key=>quote(row[key])).join(',')).join('\r\n')+'\r\n';
}
