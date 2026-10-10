// Pages Function: exactly two KV reads per uncached request on the Free plan.
export async function onRequestGet({env}) {
  try {
    if (!env.PUBLIC_SNAPSHOTS) throw new Error('KV binding missing');
    const pointer = await env.PUBLIC_SNAPSHOTS.get('current', {type:'json'});
    if (!pointer?.key || !/^snapshot:[a-f0-9]{64}$/.test(pointer.key))
      throw new Error('Public snapshot pointer missing');
    let payload = await env.PUBLIC_SNAPSHOTS.get(pointer.key, {type:'arrayBuffer'});
    if (!payload && /^snapshot:[a-f0-9]{64}$/.test(pointer.previous_key || ''))
      payload = await env.PUBLIC_SNAPSHOTS.get(pointer.previous_key, {type:'arrayBuffer'});
    if (!payload) throw new Error('Public snapshot object missing');
    return new Response(payload, {encodeBody:'manual', headers:{'content-type':'application/json; charset=utf-8',
      'content-encoding':'gzip',
      'cache-control':'public, max-age=60, stale-while-revalidate=300',
      'x-content-type-options':'nosniff'}});
  } catch (_) {
    return Response.json({manifest:{schema_version:1,data_status:'unknown'},
      events:[],incidents:[],matches:[],sources:[],details:{},error:'snapshot_unavailable'},
    {status:503,headers:{'cache-control':'no-store',
      'x-public-binding':env.PUBLIC_SNAPSHOTS ? 'ready' : 'missing'}});
  }
}
