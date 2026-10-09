import test from 'node:test';
import assert from 'node:assert/strict';
import {onRequestGet} from './snapshot.js';

test('returns current snapshot with two reads', async () => {
  const calls = [];
  const env = {PUBLIC_SNAPSHOTS:{get:async key => {
    calls.push(key); return key === 'current' ? {key:`snapshot:${'a'.repeat(64)}`} : '{"ok":true}';
  }}};
  const response = await onRequestGet({env});
  assert.equal(response.status,200);
  assert.deepEqual(await response.json(),{ok:true});
  assert.equal(calls.length,2);
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
