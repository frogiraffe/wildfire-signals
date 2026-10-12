const longitude = value => ((value + 180) % 360 + 360) % 360 - 180;

export function summarizeArea(snapshot, bounds, hours, now = new Date(), source = 'all') {
  const end = now.getTime();
  const start = end - hours * 3_600_000;
  const midpoint = start + (end - start) / 2;
  const fullLongitude = bounds.east - bounds.west >= 360;
  const west = longitude(bounds.west);
  const east = longitude(bounds.east);
  const locations = new Map();
  let candidateCount = 0;
  let latest = -Infinity;
  let recentCount = 0;
  let earlierCount = 0;

  for (const item of snapshot.events || []) {
    const observed = Date.parse(item.observed_at);
    const lon = longitude(item.longitude);
    const insideLongitude = fullLongitude || (west <= east
      ? lon >= west && lon <= east : lon >= west || lon <= east);
    if (!Number.isFinite(observed) || observed < start || observed > end ||
        !Number.isFinite(item.latitude) || !Number.isFinite(item.longitude) ||
        item.latitude < bounds.south || item.latitude > bounds.north ||
        !insideLongitude ||
        (source !== 'all' && !(item.sources || []).includes(source))) continue;

    candidateCount++;
    latest = Math.max(latest,observed);
    if (observed >= midpoint) recentCount++;
    else earlierCount++;
    const location = `${item.latitude},${lon}`;
    locations.set(location,(locations.get(location) || 0) + 1);
  }

  return {candidateCount,locationCount:locations.size,
    repeatedLocationCount:[...locations.values()].filter(count => count >= 2).length,
    latestObservedAt:Number.isFinite(latest) ? new Date(latest).toISOString()
      .replace('.000Z','Z') : null,
    recentCount,earlierCount,comparisonHours:hours / 2,
    sourceProblems:(snapshot.sources || []).filter(row =>
      row.key?.startsWith('VIIRS_') && row.status !== 'complete')
      .map(row => row.key)};
}

export function investigationLeads(snapshot, bounds, hours, now = new Date(),
  source = 'all', limit = 5) {
  const end = now.getTime();
  const start = end - hours * 3_600_000;
  const recentStart = Math.max(start, end - 12 * 3_600_000);
  const fullLongitude = bounds.east - bounds.west >= 360;
  const west = longitude(bounds.west);
  const east = longitude(bounds.east);
  const cells = new Map();

  for (const item of snapshot.events || []) {
    const observed = Date.parse(item.observed_at);
    const lon = longitude(item.longitude);
    const insideLongitude = fullLongitude || (west <= east
      ? lon >= west && lon <= east : lon >= west || lon <= east);
    if (!Number.isFinite(observed) || observed < start || observed > end ||
        !Number.isFinite(item.latitude) || !Number.isFinite(item.longitude) ||
        item.latitude < bounds.south || item.latitude > bounds.north ||
        !insideLongitude ||
        (source !== 'all' && !(item.sources || []).includes(source))) continue;

    const normalizedLon = Number(lon.toFixed(4));
    const key = `${item.latitude},${normalizedLon}`;
    let cell = cells.get(key);
    if (!cell) {
      cell = {latitude:item.latitude,longitude:normalizedLon,hours:new Set(),sources:new Set(),
        latest:-Infinity,eventId:null};
      cells.set(key,cell);
    }
    cell.hours.add(Math.floor(observed / 3_600_000));
    for (const name of item.sources || []) cell.sources.add(name);
    if (observed > cell.latest) {
      cell.latest = observed;
      cell.eventId = item.event_id;
    }
  }

  return [...cells.values()].filter(cell => cell.latest >= recentStart)
    .sort((a,b) => (b.hours.size >= 2) - (a.hours.size >= 2) ||
      b.latest - a.latest || b.hours.size - a.hours.size ||
      a.latitude - b.latitude || a.longitude - b.longitude)
    .slice(0,Math.max(0,limit)).map(cell => ({latitude:cell.latitude,
      longitude:cell.longitude,observedHours:cell.hours.size,
      latestObservedAt:new Date(cell.latest).toISOString().replace('.000Z','Z'),
      eventId:cell.eventId,sources:[...cell.sources].sort()}));
}
