// Exact-identity NIFC perimeter context. A mapped boundary is not a spread forecast.
const ENDPOINT = 'https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/' +
  'services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query';
const IRWIN_ID = /^\{[a-f\d]{8}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{4}-[a-f\d]{12}\}$/i;
const MAX_FEATURES = 10;
const MAX_VERTICES = 15_000;

function validGeometry(geometry) {
  const polygons = geometry?.type === 'Polygon' ? [geometry.coordinates]
    : geometry?.type === 'MultiPolygon' ? geometry.coordinates : null;
  if (!Array.isArray(polygons) || !polygons.length) return false;
  let vertices = 0;
  for (const polygon of polygons) {
    if (!Array.isArray(polygon) || !polygon.length) return false;
    for (const ring of polygon) {
      if (!Array.isArray(ring) || ring.length < 4) return false;
      vertices += ring.length;
      if (vertices > MAX_VERTICES) return false;
      for (const point of ring) {
        if (!Array.isArray(point) || point.length < 2 ||
            !Number.isFinite(point[0]) || !Number.isFinite(point[1]) ||
            Math.abs(point[0]) > 180 || Math.abs(point[1]) > 90) return false;
      }
      const first = ring[0], last = ring.at(-1);
      if (first[0] !== last[0] || first[1] !== last[1]) return false;
    }
  }
  return true;
}

export function parseNifcPerimeter(data, officialId, now = new Date()) {
  if (!IRWIN_ID.test(officialId)) throw new Error('invalid NIFC incident ID');
  const instant = now.getTime();
  if (!Number.isFinite(instant)) throw new Error('invalid current time');
  const features = data?.features;
  if (data?.type !== 'FeatureCollection' || !Array.isArray(features) ||
      data.exceededTransferLimit || features.length > MAX_FEATURES || data.error) {
    throw new Error('NIFC perimeter response incomplete');
  }
  if (!features.length) return {status:'not_listed',observedAt:null,stale:null,
    geojson:{type:'FeatureCollection',features:[]}};
  const checked = features.map(feature => {
    const properties = feature?.properties;
    const observed = properties?.poly_PolygonDateTime;
    if (feature?.type !== 'Feature' || properties?.poly_IRWINID !== officialId ||
        properties?.attr_IncidentTypeCategory !== 'WF' ||
        !Number.isFinite(observed) || observed <= 0 || observed > instant + 5 * 60_000 ||
        !validGeometry(feature.geometry)) throw new Error('NIFC perimeter identity or geometry invalid');
    return {observed,geometry:feature.geometry};
  });
  const latest = Math.max(...checked.map(row => row.observed));
  return {status:'mapped',observedAt:new Date(latest).toISOString(),
    stale:instant - latest > 48 * 3_600_000,
    geojson:{type:'FeatureCollection',features:checked.filter(row => row.observed === latest)
      .map(row => ({type:'Feature',properties:{},geometry:row.geometry}))}};
}

export async function fetchNifcPerimeter(officialId, {
  fetchImpl = globalThis.fetch, now = () => new Date(), signal,
} = {}) {
  if (!IRWIN_ID.test(officialId)) throw new Error('invalid NIFC incident ID');
  const url = new URL(ENDPOINT);
  url.search = new URLSearchParams({f:'geojson',
    where:`poly_IRWINID='${officialId}' AND attr_IncidentTypeCategory='WF'`,
    outFields:'poly_IRWINID,poly_PolygonDateTime,poly_IncidentName,attr_IncidentTypeCategory',
    returnGeometry:'true',outSR:'4326',maxAllowableOffset:'0.001',
    resultRecordCount:String(MAX_FEATURES)}).toString();
  const response = await fetchImpl(url.toString(),
    {headers:{Accept:'application/geo+json'},signal});
  if (!response.ok) throw new Error(`NIFC perimeter HTTP ${response.status}`);
  const raw = await response.text();
  if (raw.length > 1_000_000) throw new Error('NIFC perimeter exceeds pilot limit');
  const receivedAt = now().toISOString();
  return {...parseNifcPerimeter(JSON.parse(raw),officialId,new Date(receivedAt)),
    receivedAt,sourceUrl:url.toString()};
}
