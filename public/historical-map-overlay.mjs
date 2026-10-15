import {validateSpatialRecurrence,selectSpatialRecurrence} from './analytics-data.mjs';
export const STUDIES={ANTALYA_25KM:{name:'Antalya',lat:36.8987,lon:30.8005},DALAMAN_25KM:{name:'Dalaman',lat:36.7131,lon:28.7925}};
export function archivedGeojson(report,study,sensor='all'){
  validateSpatialRecurrence(report);
  if(!Object.hasOwn(STUDIES,study)||!['all','VIIRS_NOAA20_STANDARD','VIIRS_SNPP_STANDARD'].includes(sensor))
    throw new Error('Invalid archived map selection');
  const region=selectSpatialRecurrence(report,study);
  const features=region.published_bins.flatMap(bin=>{
    const pixels=sensor==='all'?bin.raw_pixels:bin.provider_counts?.[sensor]??0;
    if(!pixels)return [];
    const [south,west,north,east]=bin.bounds_wgs84;
    if(![south,west,north,east].every(Number.isFinite)||south>=north||west>=east)
      throw new Error('Invalid archived bin geometry');
    return [{type:'Feature',geometry:{type:'Polygon',coordinates:[[
      [west,south],[east,south],[east,north],[west,north],[west,south]
    ]]},properties:{id:bin.bin_id,pixels,classification:bin.classification,
      distinctDates:bin.distinct_dates,sourceIdentity:'unresolved'}}];
  });
  return {type:'FeatureCollection',features};
}
export function historicalStudyUrl(study){
  if(!Object.hasOwn(STUDIES,study))throw new Error('Unknown study');
  return './analytics.html#study='+encodeURIComponent(study);
}
