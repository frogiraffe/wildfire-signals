// Reproducible selection manifest; references archived reports, not downloadable raw evidence.
export function investigationManifest({study,sensor,from,to,metric,gridFilter}) {
  if(!['ANTALYA_25KM','DALAMAN_25KM'].includes(study)||
    !['all','VIIRS_NOAA20_STANDARD','VIIRS_SNPP_STANDARD'].includes(sensor)||
    !/^\d{4}-(0[1-9]|1[0-2])$/.test(from)||
    !/^\d{4}-(0[1-9]|1[0-2])$/.test(to)||
    from>to||from<'2023-01'||to>'2025-12'||
    !['raw_pixels','candidate_cell_hours'].includes(metric)||
    !['all','observed_thermal_candidate','recurrently_observed_candidate','potential_static_thermal_source'].includes(gridFilter))
    throw new Error('Invalid research investigation selection');
  const url=study==='ANTALYA_25KM'?'antalya':'dalaman';
  return {schema_version:1,kind:'retrospective_investigation_selection',study,sensor,
    annual_month_window_utc:{from,to},timeline_metric:metric,spatial_grid_classification:gridFilter,
    spatial_grid_period_utc:{from:'2023-01',to:'2025-12',month_filter_applied:false},
    sources:{annual:'./data/'+url+'-annual-context-2023-2025.json',
      spatial:'./data/turkey-spatial-recurrence-2023-2025.json'},
    uncertainty:{satellite_acquisition_exposure_verified:false,
      independent_fire_outcomes_verified:false,fire_risk_estimate:null},
    note:'This file records filter choices and source paths, not underlying evidence bytes or independently verified wildfire outcomes.'};
}
