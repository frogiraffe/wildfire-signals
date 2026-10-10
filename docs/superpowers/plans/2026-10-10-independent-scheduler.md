# Independent Scheduler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent Free Cloudflare Cron Trigger that starts the existing GitHub collector only when its latest verified scan is stale.

**Architecture:** A scheduled-only Worker reads the existing KV pointer and a short-lived dispatch marker, then makes a non-forced GitHub workflow-dispatch request. GitHub remains the collector and final Free/cadence gate. A manual GitHub deployment workflow provisions the Worker after new scoped secrets are available.

**Tech Stack:** Cloudflare Workers JavaScript, Node test runner, GitHub Actions, existing Python collector.

**Spec:** `docs/superpowers/specs/2026-10-10-independent-scheduler-design.md`

## Global constraints

- Workers Free only, no paid plan, R2, custom domain or public Worker route.
- Keep GitHub's existing scheduler, Free guard, concurrency and 55-minute collector interval.
- New tokens are secrets scoped to one repository/account and never enter source or logs.
- Docker is not used.

## Review focus

- A fresh pointer or recent dispatch marker causes zero GitHub requests or KV writes.
- Malformed/future pointer or KV error stops before dispatch.
- GitHub error does not set the dispatch marker.
- A non-forced dispatch cannot bypass the collector's 55-minute guard.
- Missing secrets or non-Free Cloudflare plan stops deployment.

---

### Task 1: Safe workflow-dispatch input

**Files:** Modify `.github/workflows/collect.yml`; test via a live manual `force_collection=false` run after merge.

- [ ] Add `workflow_dispatch.inputs.force_collection` boolean, default true; use it for `FORCE_COLLECTION` while `schedule` stays false.
- [ ] Verify a non-forced dispatch skips provider reads and KV writes while the pointer is recent.

### Task 2: Cron Worker behavior

**Files:** Create `scheduler-worker/src/index.mjs`, `scheduler-worker/wrangler.jsonc`, `tests/js/scheduler.test.mjs`.

- [ ] Write tests first for fresh/stale/absent/bad pointers, dispatch marker, failed API and exact non-forced request; observe failure.
- [ ] Implement the scheduled handler and fail-closed checks; observe tests pass.
- [ ] Configure one 15-minute Cron Trigger, existing KV binding, no public route, required GitHub secret.

### Task 3: Guarded deployment

**Files:** Create `.github/workflows/deploy-scheduler.yml`; update `README.md`.

- [ ] Add a manual-only deploy workflow that requires two new secrets and verifies the existing Free subscription gate before deployment.
- [ ] Install pinned Wrangler on Node 24; deploy with the GitHub dispatch token as a Worker secret without printing it.
- [ ] Document exact secret scopes, dashboard links, Free limits and live acceptance steps.

### Task 4: Verify and deliver

- [ ] Run complete Python and Node suites and `git diff --check`.
- [ ] Review the branch for token exposure, duplicate dispatch, and Free limits; fix findings.
- [ ] Merge public `main` and push; run a non-forced dispatch against a recent pointer.
- [ ] If the new secrets exist, deploy the Worker and observe a Cron-triggered dispatch. Otherwise, report the missing credential gate precisely and leave the existing map running.
- [ ] Update the private single-file status report with observed evidence and any remaining gap.
