# Hourly Schedule Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce missed hourly collection windows without duplicating FIRMS downloads or KV writes when GitHub schedules run late.

**Architecture:** Run the same GitHub workflow at minutes 17 and 47. Before source collection, read the latest public snapshot, falling back to the KV pointer timestamp when readback fails. Skip scheduled runs whose last scan is under 55 minutes old or cannot be verified, except an empty namespace may seed itself. Manual dispatch remains able to force a collection for repairs. No additional hosting service or paid runner is introduced.

**Tech Stack:** Python unittest, GitHub Actions schedule, Cloudflare Pages/KV Free.

**Spec:** Existing hourly `collect.yml` and the seven-day live continuity requirement in `README.md`.

## Task 1: Duplicate prevention

- [x] Add a failing test for a recent snapshot causing the collector to skip before any provider or KV write.
- [x] Add boundary cases: 54 minutes skips, 55 minutes collects, missing/naive/future timestamps skip scheduled work, empty namespace seeds, expired snapshot recovers, manual force collects.
- [x] Implement a small timestamp guard in `fire_public/cli.py`, preserving the Free plan check before any write.
- [x] Run full Python and Node suites.

## Task 2: Second schedule and live check

- [x] Add minute 47 to `collect.yml`; set `FORCE_COLLECTION` only for `workflow_dispatch`.
- [ ] Run the workflow manually to prove forced collection still works; inspect events/errors and public snapshot.
- [x] Document the fallback and the fact GitHub schedule can still delay or omit both ticks.

## Review Focus

- Missing public snapshot must use KV pointer time; absent pointer means fresh bootstrap. Invalid or future-dated timestamps must skip scheduled collection and require recovery or manual repair.
- Manual repair runs must bypass the schedule guard.
- Skipped runs must make no FIRMS, NIFC, CWFIS or KV write calls.
- Repeated manual override runs can exhaust Free storage but must never upgrade or incur overage charges.

Ruling: Use 55 rather than 60 minutes. A :17 run that starts slightly early next hour should collect; the seven-day theoretical ceiling remains below 1 GB even at one maximum-size value every 55 minutes. Scheduled work fails closed when the prior timestamp is unverifiable, but a missing pointer permits the first seed. Cost if wrong: source reads or manual overrides may still consume quota; Free quota failure would make the map stale.
