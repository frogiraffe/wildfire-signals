// Source-record changes observed by this map, not fire progression.
export function incidentTimeline(snapshot, incident) {
  if (!incident?.provider || !incident?.official_id) return [];
  const rows = snapshot?.details?.incident_history?.[`${incident.provider}:${incident.official_id}`];
  const scan = Date.parse(snapshot?.manifest?.last_scan_at);
  if (!Array.isArray(rows) || !Number.isFinite(scan)) return [];
  return rows.filter(row => row && ['first_seen','record_changed'].includes(row.change)
    && Number.isFinite(Date.parse(row.seen_at)) && Date.parse(row.seen_at) <= scan)
    .sort((a,b) => Date.parse(a.seen_at) - Date.parse(b.seen_at));
}
