// Map-only observation slices: descriptive UTC windows, not fire animation.
export function observationSlice(events, hours, slice, now = new Date()) {
  if (slice === 'all') return events;
  const index = Number(slice);
  if (![0, 1, 2].includes(index) || !Number.isInteger(index)) return events;
  const end = now.getTime();
  const start = end - hours * 3600_000;
  const interval = (end - start) / 3;
  const low = start + index * interval;
  const high = index === 2 ? end : low + interval;
  return events.filter(item => {
    const stamp = Date.parse(item.observed_at);
    return Number.isFinite(stamp) && stamp >= low &&
      (index === 2 ? stamp <= high : stamp < high);
  });
}
