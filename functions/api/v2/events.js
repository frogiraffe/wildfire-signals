import {readSnapshot,json,unavailable} from '../../../worker/snapshot-data.js';

function boundedInt(raw, fallback, min, max) {
  if (raw === null) return fallback;
  if (!/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  return Number.isSafeInteger(n) && n >= min && n <= max ? n : null;
}

function box(raw) {
  if (raw === null) return null;
  const values = raw.split(',').map(Number);
  if (values.length !== 4 || values.some(value => !Number.isFinite(value))) return false;
  const [west,south,east,north] = values;
  return west >= -180 && west <= 180 && east >= -180 && east <= 180
    && south >= -90 && north <= 90 && south <= north ? values : false;
}

export async function onRequestGet({env,request}) {
  const query = new URL(request.url).searchParams;
  const limit = boundedInt(query.get('limit'),100,1,200);
  const offset = boundedInt(query.get('offset'),0,0,1_000_000);
  const bbox = box(query.get('bbox'));
  const kind = query.get('kind');
  if (limit === null || offset === null || bbox === false
      || (kind && !['satellite_candidate','agency_incident'].includes(kind)))
    return json({error:'invalid_query'},400);
  let snapshot;
  try { snapshot = await readSnapshot(env); } catch { return unavailable(); }
  const all = [...snapshot.events,...snapshot.incidents].filter(row => {
    if (kind && row.kind !== kind) return false;
    if (!bbox) return true;
    const [west,south,east,north] = bbox;
    const lon = row.longitude, lat = row.latitude;
    return Number.isFinite(lat) && Number.isFinite(lon) && lat >= south && lat <= north
      && (west <= east ? lon >= west && lon <= east : lon >= west || lon <= east);
  });
  const events = all.slice(offset,offset+limit).map(row => row.kind === 'agency_incident'
    ? {id:`${row.provider}:${row.official_id}`,kind:row.kind,name:row.name,
       latitude:row.latitude,longitude:row.longitude,observed_at:row.modified_at,
       source:row.provider}
    : {id:row.event_id,kind:row.kind,latitude:row.latitude,longitude:row.longitude,
       observed_at:row.observed_at,source:row.sources,detection_count:row.detection_count});
  return json({schema_version:2,generated_at:snapshot.manifest.generated_at,
    data_status:snapshot.manifest.data_status,events,total:all.length,
    next_offset:offset+limit < all.length ? offset+limit : null});
}
