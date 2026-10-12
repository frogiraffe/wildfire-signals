import {effectiveStatus} from './map-state.mjs';

// Four product questions, scoped to evidence already visible in one record.
// These keys describe source claims and gaps; they never represent model outputs.
export function recordAnalysis(record, kind, manifest, sources, now = new Date()) {
  const candidate = kind === 'candidate';
  const presence = candidate ? 'satellite_unconfirmed'
    : record?.provider === 'cwfis' && record?.agency_status === 'OC'
      ? 'agency_out_of_control'
      : record?.provider === 'cwfis' && record?.agency_status === 'BH'
        ? 'agency_being_held'
        : record?.provider === 'cwfis' && record?.agency_status === 'UC'
          ? 'agency_under_control' : 'agency_reported';
  const sourceKeys = candidate ? record?.sources || [] : [record?.provider];
  const sourceStates = sourceKeys.map(key => sources?.find(source => source.key === key)?.status);
  const snapshotStatus = effectiveStatus(manifest,now);
  const quality = sourceStates.some(status => ['failed','deferred'].includes(status))
    ? 'source_unavailable'
    : snapshotStatus === 'stale' ? 'snapshot_stale'
      : snapshotStatus === 'partial' ? 'other_sources_partial'
        : snapshotStatus !== 'fresh' ? 'snapshot_unavailable'
          : sourceStates.some(status => status === undefined) ? 'source_unknown'
            : 'current_snapshot';
  const timestamp = candidate ? record?.observed_at : record?.modified_at;
  const sourceTime = Number.isFinite(Date.parse(timestamp)) &&
    Date.parse(timestamp) <= now.getTime() ? timestamp : null;
  return {presence,quality,sourceTime,
    ignition:'unavailable',ignitionReason:'ignition_unvalidated',
    spread:'unavailable',spreadReason:candidate
      ? 'spread_needs_confirmed_fire' : 'spread_missing_inputs',
    ending:'unavailable',endingReason:candidate
      ? 'ending_needs_confirmed_fire' : 'ending_missing_outcomes'};
}
