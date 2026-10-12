// Pure, worldwide candidate analysis. This is NOT a wildfire detection or risk model.
const RAD = Math.PI / 180;
const RADIUS_KM = 6371.0088;

export function normalLongitude(lon) {
  return ((lon + 180) % 360 + 360) % 360 - 180;
}

export function validRegion(region) {
  return region && Number.isFinite(region.latitude) &&
    Number.isFinite(region.longitude) && Number.isFinite(region.radiusKm) &&
    region.latitude >= -90 && region.latitude <= 90 &&
    region.longitude >= -180 && region.longitude <= 180 &&
    region.radiusKm > 0 && region.radiusKm <= 250;
}

export function distanceKm(lat1, lon1, lat2, lon2) {
  const a = lat1 * RAD, b = lat2 * RAD;
  const dlat = (lat2 - lat1) * RAD;
  const dlon = normalLongitude(lon2 - lon1) * RAD;
  const h = Math.sin(dlat / 2) ** 2 +
    Math.cos(a) * Math.cos(b) * Math.sin(dlon / 2) ** 2;
  return 2 * RADIUS_KM * Math.asin(Math.sqrt(Math.min(1, Math.max(0, h))));
}

export function circleBoundary(region, steps = 90) {
  if (!validRegion(region) || !Number.isInteger(steps) || steps < 16 || steps > 360)
    throw new RangeError('Invalid worldwide region boundary');
  const phi = region.latitude * RAD, lambda = region.longitude * RAD;
  const angular = region.radiusKm / RADIUS_KM;
  const points = [];
  for (let i = 0; i <= steps; i++) {
    const bearing = 2 * Math.PI * i / steps;
    const sinLat = Math.sin(phi) * Math.cos(angular) +
      Math.cos(phi) * Math.sin(angular) * Math.cos(bearing);
    const lat = Math.asin(Math.max(-1, Math.min(1, sinLat)));
    const lon = lambda + Math.atan2(
      Math.sin(bearing) * Math.sin(angular) * Math.cos(phi),
      Math.cos(angular) - Math.sin(phi) * Math.sin(lat));
    points.push([normalLongitude(lon / RAD), lat / RAD]);
  }
  // Split lines at the antimeridian to avoid drawing a misleading world-spanning edge.
  const segments = [];
  let line = [points[0]];
  for (let i = 1; i < points.length; i++) {
    const [alon, alat] = points[i - 1], [blon, blat] = points[i];
    if (Math.abs(blon - alon) > 180) {
      const adjusted = blon + (blon < alon ? 360 : -360);
      const seam = alon > 0 ? 180 : -180;
      const ratio = (seam - alon) / (adjusted - alon);
      const crossingLat = alat + (blat - alat) * ratio;
      line.push([seam, crossingLat]);
      if (line.length > 1) segments.push(line);
      line = [[-seam, crossingLat], [blon, blat]];
    } else line.push(points[i]);
  }
  if (line.length > 1) segments.push(line);
  return {type:'FeatureCollection', features:[{
    type:'Feature',properties:{kind:'selected-region'},
    geometry:{type:'MultiLineString',coordinates:segments}}]};
}

export function analyzeRegion(snapshot, region, hours, source = 'all', now = new Date()) {
  if (!validRegion(region) || ![6, 24, 72].includes(hours))
    throw new RangeError('Invalid region or time window');
  const end = now.getTime();
  const scan = Date.parse(snapshot?.manifest?.last_scan_at);
  const available = Number.isFinite(scan) && scan <= end + 60_000;
  const begin = end - hours * 3_600_000;
  const bins = Array.from({length:6}, (_,i) => ({fromHoursAgo: hours - i * hours / 6,
    toHoursAgo: hours - (i + 1) * hours / 6, count:0}));
  const cells = new Map();
  const sources = new Map();
  let latest = -Infinity;
  let count = 0;
  if (available) for (const event of snapshot.events || []) {
    const observed = Date.parse(event.observed_at);
    if (!Number.isFinite(observed) || observed < begin || observed > Math.min(end,scan) ||
        !Number.isFinite(event.latitude) || !Number.isFinite(event.longitude) ||
        event.latitude < -90 || event.latitude > 90 ||
        (source !== 'all' && !(event.sources || []).includes(source)) ||
        distanceKm(region.latitude,region.longitude,event.latitude,event.longitude) > region.radiusKm)
      continue;
    // FIRMS is aggregated into 0.05-degree cell-hours; prevent duplicate cell-hours.
    const lat = Number(event.latitude.toFixed(4));
    const lon = Number(normalLongitude(event.longitude).toFixed(4));
    const hour = Math.floor(observed / 3_600_000);
    const cellKey = lat + ',' + lon;
    let cell = cells.get(cellKey);
    if (!cell) {
      cell = {latitude:lat,longitude:lon,hours:new Set(),latest:-Infinity,
        eventId:null,sensors:new Set()};
      cells.set(cellKey,cell);
    }
    if (!cell.hours.has(hour)) {
      count++;
      bins[Math.min(5,Math.floor((observed - begin) / ((hours / 6) * 3_600_000)))].count++;
    }
    cell.hours.add(hour);
    for (const sensor of event.sources || []) {
      cell.sensors.add(sensor);
      sources.set(sensor,(sources.get(sensor) || 0) + 1);
    }
    if (observed > cell.latest) {
      cell.latest = observed;
      cell.eventId = event.event_id || null;
    }
    latest = Math.max(latest,observed);
  }
  const leads = [...cells.values()].sort((a,b) => b.hours.size - a.hours.size ||
    b.latest - a.latest || a.latitude - b.latitude || a.longitude - b.longitude)
    .slice(0,5).map(row => ({
      latitude:row.latitude,longitude:row.longitude,observedHours:row.hours.size,
      latestObservedAt:new Date(row.latest).toISOString(),
      eventId:row.eventId,sources:[...row.sensors].sort()
    }));
  const sourceProblems = (snapshot?.sources || []).filter(x =>
    x.key?.startsWith('VIIRS_') && x.status !== 'complete').map(x => x.key);
  const quality = !available ? 'unavailable' : end - scan > 90 * 60_000 ? 'stale' :
    sourceProblems.length || snapshot?.manifest?.data_status === 'partial' ? 'partial' : 'current';
  return {available,quality,scanAt:available ? new Date(scan).toISOString() : null,
    radiusKm:region.radiusKm,center:{latitude:region.latitude,longitude:region.longitude},
    hours,candidateCellHours:count,distinctCells:cells.size,
    recurringCells:[...cells.values()].filter(x => x.hours.size > 1).length,
    latestObservedAt:Number.isFinite(latest) ? new Date(latest).toISOString() : null,
    sensors:[...sources.entries()].sort((a,b) => a[0].localeCompare(b[0]))
      .map(([key,memberships])=>({key,memberships})),
    sourceProblems,bins,leads};
}
