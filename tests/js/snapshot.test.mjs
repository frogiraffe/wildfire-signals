import test from 'node:test';
import assert from 'node:assert/strict';
import {gzipSync,gunzipSync} from 'node:zlib';
import {onRequestGet} from '../../functions/api/snapshot.js';

test('returns current snapshot with two reads', async () => {
  const calls = [];
  const env = {PUBLIC_SNAPSHOTS:{get:async key => {
    calls.push(key); return key === 'current' ? {key:`snapshot:${'a'.repeat(64)}`} : gzipSync('{"ok":true}');
  }}};
  const response = await onRequestGet({env});
  assert.equal(response.status,200);
  assert.equal(response.headers.get('content-encoding'),'gzip');
  assert.deepEqual(JSON.parse(gunzipSync(Buffer.from(await response.arrayBuffer()))),{ok:true});
  assert.equal(calls.length,2);
});

test('precompressed KV body is sent without Worker recompression', async () => {
  const NativeResponse = globalThis.Response;
  let encodeBody;
  globalThis.Response = class extends NativeResponse {
    constructor(body, init) {
      encodeBody = init?.encodeBody;
      super(body, init);
    }
  };
  try {
    const key = `snapshot:${'f'.repeat(64)}`;
    const response = await onRequestGet({env:{PUBLIC_SNAPSHOTS:{get:async name =>
      name === 'current' ? {key} : gzipSync('{"events":[1]}')}}});
    assert.equal(encodeBody, 'manual');
    assert.equal(response.headers.get('content-encoding'), 'gzip');
  } finally {
    globalThis.Response = NativeResponse;
  }
});

test('missing shard and quota error fail closed', async () => {
  const key = `snapshot:${'b'.repeat(64)}`;
  for (const get of [async name => name === 'current' ? {key} : null,
    async () => {throw new Error('KV quota exhausted');}]) {
    const response = await onRequestGet({env:{PUBLIC_SNAPSHOTS:{get}}});
    assert.equal(response.status,503);
    assert.equal((await response.json()).error,'snapshot_unavailable');
  }
});

test('unavailable snapshot reveals only KV binding readiness', async () => {
  const missing = await onRequestGet({env:{}});
  assert.equal(missing.status,503);
  assert.equal(missing.headers.get('x-public-binding'), 'missing');
  const ready = await onRequestGet({env:{PUBLIC_SNAPSHOTS:{get:async () => null}}});
  assert.equal(ready.status,503);
  assert.equal(ready.headers.get('x-public-binding'), 'ready');
});

test('serves previous version during cross-region KV propagation', async () => {
  const old = `snapshot:${'d'.repeat(64)}`, next = `snapshot:${'e'.repeat(64)}`;
  const calls = [];
  const response = await onRequestGet({env:{PUBLIC_SNAPSHOTS:{get:async key => {
    calls.push(key);
    return key === 'current' ? {key:next,previous_key:old} :
      key === old ? gzipSync('{"version":"old"}') : null;
  }}}});
  assert.equal(response.status,200);
  assert.deepEqual(JSON.parse(gunzipSync(Buffer.from(await response.arrayBuffer()))),{version:'old'});
  assert.deepEqual(calls,['current',next,old]);
});

test('10,000 uncached visits stay within KV Free read quota', async () => {
  let reads = 0;
  const key = `snapshot:${'c'.repeat(64)}`;
  const env = {PUBLIC_SNAPSHOTS:{get:async name => {
    reads++;
    return name === 'current' ? {key} : gzipSync('{"manifest":{"schema_version":1}}');
  }}};
  for (let visit = 0; visit < 10_000; visit++) {
    const response = await onRequestGet({env});
    assert.equal(response.status,200);
  }
  assert.equal(reads,20_000);
  assert.ok(reads < 100_000);
});
