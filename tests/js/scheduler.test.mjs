import test from 'node:test';
import assert from 'node:assert/strict';
import { runSchedule, runScheduled } from '../../scheduler-worker/src/index.mjs';

const now = new Date('2026-10-10T12:00:00.000Z');
const key = `snapshot:${'a'.repeat(64)}`;

function fixture(pointer, marker = null) {
  const values = new Map();
  if (pointer !== null) values.set('current', pointer);
  if (marker !== null) values.set('scheduler:last_dispatch', marker);
  const writes = [];
  const env = {
    GITHUB_DISPATCH_TOKEN: 'test-secret',
    PUBLIC_SNAPSHOTS: {
      async get(name, type) {
        assert.equal(type, 'json');
        return values.get(name) ?? null;
      },
      async put(name, value, options) {
        writes.push({ name, value: JSON.parse(value), options });
        values.set(name, JSON.parse(value));
      },
    },
  };
  const requests = [];
  async function fetchGitHub(url, options) {
    requests.push({ url, options });
    return new Response(JSON.stringify({ workflow_run_id: 12345 }), { status: 200 });
  }
  return { env, writes, requests, fetchGitHub };
}

test('fresh pointer makes no dispatch or KV write', async () => {
  const f = fixture({ key, last_scan_at: '2026-10-10T11:10:00+00:00' });
  assert.equal(await runSchedule(f.env, now, f.fetchGitHub), 'fresh');
  assert.equal(f.requests.length, 0);
  assert.equal(f.writes.length, 0);
});

test('stale pointer dispatches once without forcing collection', async () => {
  const f = fixture({ key, last_scan_at: '2026-10-10T10:50:00+00:00' });
  assert.equal(await runSchedule(f.env, now, f.fetchGitHub), 'dispatched');
  assert.equal(f.requests.length, 1);
  assert.equal(f.requests[0].url,
    'https://api.github.com/repos/frogiraffe/wildfire-signals/actions/workflows/collect.yml/dispatches');
  assert.deepEqual(JSON.parse(f.requests[0].options.body),
    { ref: 'main', inputs: { force_collection: false } });
  assert.equal(f.requests[0].options.headers.Authorization, 'Bearer test-secret');
  assert.equal(f.requests[0].options.headers['User-Agent'],
    'wildfire-signals-scheduler');
  assert.deepEqual(f.writes, [{ name: 'scheduler:last_dispatch',
    value: { last_dispatch_at: '2026-10-10T12:00:00.000Z' },
    options: { expirationTtl: 3600 } }]);
  assert.equal(await runSchedule(f.env, new Date('2026-10-10T12:15:00Z'), f.fetchGitHub),
    'recent_dispatch');
  assert.equal(f.requests.length, 1);
});

test('absent pointer requests a non-forced bootstrap run', async () => {
  const f = fixture(null);
  assert.equal(await runSchedule(f.env, now, f.fetchGitHub), 'dispatched');
  assert.equal(f.requests.length, 1);
  assert.deepEqual(JSON.parse(f.requests[0].options.body).inputs,
    { force_collection: false });
});

test('invalid or future pointer stops before GitHub call', async () => {
  for (const pointer of [
    { key, last_scan_at: 'bad-date' },
    { key, last_scan_at: '2026-10-10T12:05:00Z' },
    { key, last_scan_at: '2026-10-10T10:00:00' },
    { key: 'wrong', last_scan_at: '2026-10-10T10:00:00Z' },
  ]) {
    const f = fixture(pointer);
    await assert.rejects(runSchedule(f.env, now, f.fetchGitHub));
    assert.equal(f.requests.length, 0);
    assert.equal(f.writes.length, 0);
  }
});

test('KV failure and recent dispatch marker stop before GitHub call', async () => {
  const f = fixture({ key, last_scan_at: '2026-10-10T10:00:00Z' },
    { last_dispatch_at: '2026-10-10T11:30:00Z' });
  assert.equal(await runSchedule(f.env, now, f.fetchGitHub), 'recent_dispatch');
  assert.equal(f.requests.length, 0);
  const broken = fixture(null);
  broken.env.PUBLIC_SNAPSHOTS.get = async () => { throw new Error('KV unavailable'); };
  await assert.rejects(runSchedule(broken.env, now, broken.fetchGitHub), /KV unavailable/);
  assert.equal(broken.requests.length, 0);
});

test('invalid or future dispatch marker fails closed', async () => {
  for (const marker of [
    { last_dispatch_at: 'bad-date' },
    { last_dispatch_at: '2026-10-10T12:05:00Z' },
    { last_dispatch_at: '2026-10-10T11:30:00' },
    {},
  ]) {
    const f = fixture({ key, last_scan_at: '2026-10-10T10:00:00Z' }, marker);
    await assert.rejects(runSchedule(f.env, now, f.fetchGitHub));
    assert.equal(f.requests.length, 0);
    assert.equal(f.writes.length, 0);
  }
});

test('GitHub legacy 204 acceptance records the dispatch marker', async () => {
  const f = fixture({ key, last_scan_at: '2026-10-10T10:00:00Z' });
  assert.equal(await runSchedule(f.env, now,
    async () => new Response(null, { status: 204 })), 'dispatched');
  assert.equal(f.writes.length, 1);
});

test('failed GitHub dispatch does not write the marker', async () => {
  const f = fixture({ key, last_scan_at: '2026-10-10T10:00:00Z' });
  await assert.rejects(runSchedule(f.env, now, async () => new Response('unavailable', {
    status: 503,
  })), /GitHub dispatch failed: 503/);
  assert.equal(f.writes.length, 0);
});

test('scheduled invocation records an eight-day receipt even when no dispatch is needed', async () => {
  const f = fixture({ key, last_scan_at: '2026-10-10T11:10:00+00:00' });
  assert.equal(await runScheduled(f.env, now, f.fetchGitHub), 'fresh');
  assert.deepEqual(f.writes, [{
    name: 'scheduler:tick:2026-10-10T12:00:00.000Z',
    value: { at: '2026-10-10T12:00:00.000Z', outcome: 'fresh' },
    options: { expirationTtl: 8 * 86400 },
  }]);
});

test('scheduled failure records a receipt without dispatching', async () => {
  const f = fixture({ key: 'invalid', last_scan_at: '2026-10-10T10:00:00Z' });
  await assert.rejects(runScheduled(f.env, now, f.fetchGitHub), /current pointer is invalid/);
  assert.deepEqual(f.writes, [{
    name: 'scheduler:tick:2026-10-10T12:00:00.000Z',
    value: { at: '2026-10-10T12:00:00.000Z', outcome: 'error',
      failure: 'invalid_pointer' },
    options: { expirationTtl: 8 * 86400 },
  }]);
  assert.equal(f.requests.length, 0);
});

test('scheduled GitHub rejection records status without a token or response body', async () => {
  const f = fixture({ key, last_scan_at: '2026-10-10T10:00:00Z' });
  await assert.rejects(runScheduled(f.env, now,
    async () => new Response('possibly sensitive', { status: 403 })),
    /GitHub dispatch failed: 403/);
  assert.deepEqual(f.writes[0].value,
    { at: '2026-10-10T12:00:00.000Z', outcome: 'error', failure: 'github_http_403' });
});
