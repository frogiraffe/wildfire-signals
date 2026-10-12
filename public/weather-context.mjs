// NWS grid forecast context for a selected US location. No fire inference.
const HOURS = [0, 6, 12, 24];
const nonnegative = value => value >= 0;
const FIELDS = {
  windSpeed:['wmoUnit:km_h-1','windKmh',nonnegative],
  windDirection:['wmoUnit:degree_(angle)','directionDeg',value => value >= 0 && value <= 360],
  windGust:['wmoUnit:km_h-1','gustKmh',nonnegative],
  temperature:['wmoUnit:degC','temperatureC',value => value >= -100 && value <= 70],
  relativeHumidity:['wmoUnit:percent','humidityPercent',value => value >= 0 && value <= 100],
};

function interval(validTime) {
  if (typeof validTime !== 'string') return null;
  const [startText,duration] = validTime.split('/');
  const start = Date.parse(startText);
  const match = /^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$/.exec(duration || '');
  if (!Number.isFinite(start) || !match) return null;
  const ms = (+match[1] || 0) * 86_400_000 + (+match[2] || 0) * 3_600_000
    + (+match[3] || 0) * 60_000 + (+match[4] || 0) * 1000;
  if (!ms || ms > 8 * 86_400_000) return null;
  return {start,end:start + ms,startText};
}

function valueAt(field, unit, instant, valid = () => true) {
  if (field?.uom !== unit || !Array.isArray(field.values)) return null;
  for (const entry of field.values) {
    const period = interval(entry?.validTime);
    if (period && period.start <= instant && instant < period.end &&
        typeof entry.value === 'number' && Number.isFinite(entry.value) && valid(entry.value)) {
      return {value:entry.value,period};
    }
  }
  return null;
}

export function parseNwsGrid(grid, now = new Date()) {
  const properties = grid?.properties;
  const updatedAt = properties?.updateTime;
  const updated = Date.parse(updatedAt);
  const current = now.getTime();
  if (!Number.isFinite(updated) || !Number.isFinite(current)) {
    throw new Error('NWS forecast update time unavailable');
  }
  if (updated > current + 5 * 60_000) throw new Error('NWS forecast update is in the future');
  const rows = HOURS.map(hours => {
    const target = current + hours * 3_600_000;
    const row = {hours,validAt:new Date(target).toISOString(),validity:{}};
    for (const [name,[unit,key,valid]] of Object.entries(FIELDS)) {
      const measurement = valueAt(properties[name],unit,target,valid);
      row[key] = measurement?.value ?? null;
      row.validity[key] = measurement ? {start:measurement.period.startText,
        end:new Date(measurement.period.end).toISOString()} : null;
    }
    const rain = valueAt(properties.quantitativePrecipitation,'wmoUnit:mm',target,nonnegative);
    row.rain = rain ? {mm:rain.value,start:rain.period.startText,
      end:new Date(rain.period.end).toISOString()} : null;
    return row;
  });
  if (rows.every(row => row.windKmh === null && row.temperatureC === null)) {
    throw new Error('NWS forecast has no usable values');
  }
  return {updatedAt,stale:current - updated > 12 * 3_600_000,rows};
}

export function forecastChanges(forecast) {
  const rows = forecast?.rows;
  if (!Array.isArray(rows) || !rows.length ||
      rows.some(row => !row || ![0,6,12,24].includes(row.hours)) ||
      new Set(rows.map(row => row.hours)).size !== rows.length) return [];
  const baseline = rows.find(row => row.hours === 0);
  if (!baseline) return [];
  const change = (before, after) =>
    Number.isFinite(before) && Number.isFinite(after) ? after - before : null;
  return rows.filter(row => row.hours !== 0).sort((a,b) => a.hours - b.hours)
    .map(row => ({hours:row.hours,
      windKmh:change(baseline.windKmh,row.windKmh),
      gustKmh:change(baseline.gustKmh,row.gustKmh),
      temperatureC:change(baseline.temperatureC,row.temperatureC),
      humidityPercent:change(baseline.humidityPercent,row.humidityPercent),
      directionTurnDeg: Number.isFinite(baseline.directionDeg) &&
        Number.isFinite(row.directionDeg)
        ? ((row.directionDeg - baseline.directionDeg + 540) % 360) - 180 : null}));
}

async function readJson(url, fetchImpl, signal) {
  const response = await fetchImpl(url,{headers:{Accept:'application/geo+json'},signal});
  if (!response.ok) throw new Error(`NWS HTTP ${response.status}`);
  const raw = await response.text();
  if (raw.length > 1_000_000) throw new Error('NWS response exceeds pilot limit');
  return JSON.parse(raw);
}

export async function fetchNwsWeather(latitude, longitude, {
  fetchImpl = globalThis.fetch, now = () => new Date(), signal,
} = {}) {
  if (![latitude,longitude].every(Number.isFinite) || Math.abs(latitude) > 90 ||
      Math.abs(longitude) > 180) throw new Error('invalid location');
  const pointUrl = `https://api.weather.gov/points/${latitude.toFixed(4)},${longitude.toFixed(4)}`;
  const point = await readJson(pointUrl,fetchImpl,signal);
  const sourceUrl = point?.properties?.forecastGridData;
  if (typeof sourceUrl !== 'string' ||
      !/^https:\/\/api\.weather\.gov\/gridpoints\/[A-Z]{3}\/\d+,\d+$/.test(sourceUrl)) {
    throw new Error('NWS grid URL unavailable or invalid');
  }
  const grid = await readJson(sourceUrl,fetchImpl,signal);
  const receivedAt = now().toISOString();
  return {...parseNwsGrid(grid,new Date(receivedAt)),sourceUrl,receivedAt};
}
