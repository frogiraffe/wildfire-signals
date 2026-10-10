# 72-Hour Map Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing 72-hour satellite filter reflect a real rolling 72-hour global dataset without exceeding Free-plan limits.

**Architecture:** Query the four UTC calendar dates that can intersect a rolling 72-hour window, then filter records locally to exactly 72 hours. Probe NASA responses and final gzip size without publishing. Keep the current 24-hour collector live until the probe and browser checks pass.

**Tech Stack:** Python unittest, NASA FIRMS area CSV API, GitHub Actions, Cloudflare Pages/KV, Node browser smoke.

**Spec:** Existing `public/index.html` 6/24/72-hour selector and `public/map-state.mjs` rolling filter; `README.md` Free-plan budget.

## Task 1: Source window contract

- [ ] Add a failing `fetch_firms` test for a 72-hour record crossing UTC midnight and a record older than 72 hours.
- [ ] Run the focused test and confirm the URL/window failure.
- [ ] Change FIRMS day range to four UTC dates and local filter to 72 hours.
- [ ] Run Python and Node test suites; commit to probe branch.

## Task 2: Read-only provider and size probe

- [ ] Run the source-only pilot from the probe branch with no Cloudflare credentials or writes.
- [ ] Confirm both FIRMS sources complete, raw responses stay within 50 MiB and 250,000 rows per source, gzip stays below 5 MiB, and the candidate count exceeds the 24-hour baseline.
- [ ] If a gate fails, leave the live collector unchanged and remove the misleading 72-hour UI option instead.

## Task 3: Live acceptance

- [ ] Merge the proven change to `main`, let Pages deploy, and run the collector manually once.
- [ ] Confirm events, errors, endpoint gzip/JSON, and desktop/mobile browser checks; keep the hourly schedule enabled.
- [ ] Update the public README and private single-file status report with measured limits and unresolved seven-day acceptance.

## Review Focus

- UTC day boundary must include the previous third day.
- The local 72-hour cutoff must reject older records even when NASA returns them.
- Source and KV byte/row limits must remain fail-closed.
- No Cloudflare write may occur during the source-only probe.
