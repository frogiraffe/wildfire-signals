import {readSnapshot,json,unavailable} from '../../../../worker/snapshot-data.js';

export async function onRequestGet({env,params}) {
  let id;
  try { id = decodeURIComponent(params.id || ''); } catch { return json({error:'invalid_id'},400); }
  if (!id || id.length > 180 || id.includes('\0')) return json({error:'invalid_id'},400);
  let snapshot;
  try { snapshot = await readSnapshot(env); } catch { return unavailable(); }
  const agency = snapshot.incidents.find(row => `${row.provider}:${row.official_id}` === id);
  const candidate = agency ? null : snapshot.events.find(row => row.event_id === id);
  const record = agency || candidate;
  if (!record) return json({error:'event_unavailable'},404);
  const history = agency ? snapshot.details?.incident_history?.[id] || [] : [];
  return json({schema_version:2,id,kind:record.kind,
    generated_at:snapshot.manifest.generated_at,data_status:snapshot.manifest.data_status,
    observations:[record],history,
    area_history:{status:'unavailable',measurements:[]},
    conditions:{status:'unavailable',measurements:[]},
    interventions:{status:'unknown',records:[]},forecast_runs:[],
    outcomes:{growth_stopped:'unknown',active_front_receded:'unknown',
      thermal_quiet_after_observation:'unknown',agency_control:'unknown'}});
}
