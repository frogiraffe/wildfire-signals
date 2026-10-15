// Evidence audit uses only declared source claims; never infers negative wildfire labels.
export function historicalAudit(report, regionId) {
  if(report?.observation_opportunity_verified!==false||
      report?.independent_fire_outcome_valid!==false||
      !/^[a-f0-9]{64}$/.test(report.evidence_sha256??'')||
      !Array.isArray(report.regions)) throw new Error('Unverified research evidence contract');
  const region=report.regions.find(r=>r.region?.region_id===regionId);
  if(!region) throw new Error('Region not represented by archived evidence');
  const bins=region.published_bins??[];
  const mapped=bins.reduce((n,r)=>n+r.raw_pixels,0);
  if(mapped>region.selected_raw_pixels)throw new Error('Published grid population exceeds archived observations');
  return {regionId,publishedBins:bins.length,mappedPixels:mapped,
    totalPixels:region.selected_raw_pixels,unmappedPixels:region.selected_raw_pixels-mapped,
    sourceSha256:report.evidence_sha256,
    acquiredOpportunity:'unverified',verifiedNegativeEvents:0,
    validatedWildfireOutcomes:false,
    sourceIdentityVerified:false,gridIsFirePerimeter:false,
    caution:'Published grid cells are only selected archived thermal evidence; missing pixels/bins do not indicate no fire. Satellite acquisition exposure, independent outcomes, and source identities are not verified.'};
}
