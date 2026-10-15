import {validateFrapCohort} from './analytics-data.mjs';
// Source report stores ONLY bounding boxes, not actual official perimeter vertices.
// Draw a dashed bounding-box evidence locator, never a filled fire polygon.
export function agencyBoundsGeojson(report) {
  validateFrapCohort(report);
  return {type:'FeatureCollection',features:report.cases.map(row=>{
    const v=row.geometry_bounds_wgs84;
    if(!v.every(Number.isFinite)||v[0]>=v[2]||v[1]>=v[3]||
      v[0]<-180||v[2]>180||v[1]<-90||v[3]>90)
      throw new Error('Invalid agency evidence bounding box');
    return {type:'Feature',geometry:{type:'Polygon',coordinates:[[
      [v[0],v[1]],[v[2],v[1]],[v[2],v[3]],[v[0],v[3]],[v[0],v[1]]
    ]]},properties:{id:row.source_object_id,name:row.source_name,
      year:row.source_year,alarmDate:row.source_alarm_date_calendar,
      method:row.source_method,status:row.evidence_status,
      boundsOnly:true,ignitionPoint:false,source:'CAL FIRE FRAP'}};
  })};
}
