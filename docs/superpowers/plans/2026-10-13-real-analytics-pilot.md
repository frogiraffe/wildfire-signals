# Real FIRMS analytics pilot implementation plan

> **For agentic workers:** Execute task by task with red-green tests and a review at each boundary.

**Goal:** Produce a reproducible real-source thermal observation dataset, descriptive comparison and experimental next-scan count baseline, with a bounded web view.

**Architecture:** Verify and index existing FIRMS GitHub Release assets into offline SQLite. Derive aggregate-only UTC scan/region rows from first-captured original pixels, then generate a static research report for the existing map. All modeling stays offline; public UI presents descriptive evidence and provenance, never wildfire probability.

**Tech Stack:** Python standard library and SQLite, existing release importer, static JavaScript and MapLibre UI, Python/Node/Playwright tests.

**Spec:** User's 2026-10-13 Statistical Analytics & Scientific Modeling Execution request; `docs/ENGINEERING_POLICY.md`.

## Global constraints

- No private repository data, raw research assets, SQLite DB or trained model binaries in Git.
- Preserve Free Pages/Functions/KV costs; add no runtime provider requests for the pilot.
- Thermal detections and provider capture counts are not confirmed wildfire events.
- Unknown observation opportunity stays unknown; sparse history cannot support seasonal or fire-occurrence claims.

## Review focus

- Multiple scan receipts inside one dated Release retain one-to-one manifest validation and atomic download.
- A failed or absent scan never becomes a zero outcome.
- Training features use only scans captured before the held-out next scan.
- Temporal and geographic holdouts do not reuse the same region/transition pair.
- Static report carries input hashes, time span and limitations without raw coordinates or source rows.

### Task 1: Repair real Release ingestion

- [x] Add a failing end-to-end test with two scans in one daily Release and per-scan pixel assets.
- [x] Verify it fails at the one-scan assumption.
- [x] Extend bounded release planning and manifest verification for multiple timestamped scans.
- [x] Re-run sync/import tests and use the actual 12–13 October public Releases offline.

### Task 2: Produce real aggregate dataset and baseline

- [x] Test scan/region/sensor aggregation, UTC buckets, incomplete source scans, as-of time and source provenance.
- [x] Test persistence and interpretable count regression with temporal and geographic holdouts.
- [x] Implement the bounded offline builder and static JSON output using the verified SQLite index.
- [x] Run it on real Releases; record counts, denominators, metrics and withheld conclusions.

### Task 3: Integrate a public research view

- [x] Test static aggregate schema, date/region filtering and missing-data language in a local browser.
- [x] Add the small generated aggregate artifact and existing-map navigation without a new framework or API/KV call.
- [x] Document data contract, pilot method, reproduction, license, limitations, backlog and maturity.
- [ ] Run PR CI, then stop before any production-changing merge. Full local suite has passed.
