const SNAPSHOT_KEY = /^snapshot:[a-f0-9]{64}$/;

export async function readSnapshot(env) {
  if (!env?.PUBLIC_SNAPSHOTS) throw new Error('KV binding missing');
  const pointer = await env.PUBLIC_SNAPSHOTS.get('current', {type:'json'});
  if (!SNAPSHOT_KEY.test(pointer?.key || '')) throw new Error('Snapshot pointer missing');
  let data = await env.PUBLIC_SNAPSHOTS.get(pointer.key, {type:'arrayBuffer'});
  if (!data && SNAPSHOT_KEY.test(pointer.previous_key || ''))
    data = await env.PUBLIC_SNAPSHOTS.get(pointer.previous_key, {type:'arrayBuffer'});
  if (!data) throw new Error('Snapshot value missing');
  const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('gzip'));
  const snapshot = await new Response(stream).json();
  if (snapshot?.manifest?.schema_version !== 1 || !Array.isArray(snapshot.events)
      || !Array.isArray(snapshot.incidents) || !Array.isArray(snapshot.sources))
    throw new Error('Invalid snapshot');
  return snapshot;
}

export function json(data, status=200) {
  return Response.json(data, {status, headers:{'cache-control':status===200
    ? 'public, max-age=60, stale-while-revalidate=300' : 'no-store',
    'x-content-type-options':'nosniff'}});
}

export function unavailable() {
  return json({error:'snapshot_unavailable'},503);
}
