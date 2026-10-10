const DISPATCH_URL = 'https://api.github.com/repos/frogiraffe/wildfire-signals/actions/workflows/collect.yml/dispatches';
const POINTER_KEY = 'current';
const DISPATCH_KEY = 'scheduler:last_dispatch';
const STALE_AFTER_MS = 65 * 60 * 1000;
const DISPATCH_INTERVAL_MS = 55 * 60 * 1000;

function verifiedTime(value, now) {
  if (typeof value !== 'string' || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    throw new Error('timestamp lacks a timezone');
  }
  const time = Date.parse(value);
  if (!Number.isFinite(time) || time > now.getTime()) {
    throw new Error('timestamp is invalid or in the future');
  }
  return time;
}

export async function runSchedule(env, now = new Date(), fetchGitHub = fetch) {
  if (!env.GITHUB_DISPATCH_TOKEN || !env.PUBLIC_SNAPSHOTS) {
    throw new Error('scheduler secrets or KV binding are missing');
  }
  const pointer = await env.PUBLIC_SNAPSHOTS.get(POINTER_KEY, 'json');
  if (pointer !== null) {
    if (typeof pointer !== 'object' ||
        !/^snapshot:[a-f0-9]{64}$/.test(pointer.key)) {
      throw new Error('current pointer is invalid');
    }
    if (now.getTime() - verifiedTime(pointer.last_scan_at, now) < STALE_AFTER_MS) {
      return 'fresh';
    }
  }
  const marker = await env.PUBLIC_SNAPSHOTS.get(DISPATCH_KEY, 'json');
  if (marker !== null) {
    if (typeof marker !== 'object') throw new Error('dispatch marker is invalid');
    if (now.getTime() - verifiedTime(marker.last_dispatch_at, now) < DISPATCH_INTERVAL_MS) {
      return 'recent_dispatch';
    }
  }
  const response = await fetchGitHub(DISPATCH_URL, {
    method: 'POST',
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${env.GITHUB_DISPATCH_TOKEN}`,
      'Content-Type': 'application/json',
      'X-GitHub-Api-Version': '2026-03-10',
    },
    body: JSON.stringify({ ref: 'main', inputs: { force_collection: false } }),
    signal: AbortSignal.timeout(15_000),
  });
  if (!response.ok) throw new Error(`GitHub dispatch failed: ${response.status}`);
  if (response.status !== 204) {
    const body = await response.json();
    if (!Number.isInteger(body.workflow_run_id)) {
      throw new Error('GitHub dispatch response has no run ID');
    }
  }
  await env.PUBLIC_SNAPSHOTS.put(DISPATCH_KEY,
    JSON.stringify({ last_dispatch_at: now.toISOString() }), { expirationTtl: 3600 });
  return 'dispatched';
}

export async function runScheduled(env, now = new Date(), fetchGitHub = fetch) {
  let outcome = 'error';
  try {
    outcome = await runSchedule(env, now, fetchGitHub);
    return outcome;
  } finally {
    // One bounded receipt per Cron invocation makes missed triggers observable.
    // A failed receipt must not prevent a successful dispatch or hide its error.
    try {
      await env.PUBLIC_SNAPSHOTS.put(`scheduler:tick:${now.toISOString()}`,
        JSON.stringify({ at: now.toISOString(), outcome }),
        { expirationTtl: 8 * 86400 });
    } catch {
      console.error('scheduler receipt write failed');
    }
  }
}

export default {
  async scheduled(_controller, env) {
    console.log(`scheduler: ${await runScheduled(env)}`);
  },
};
