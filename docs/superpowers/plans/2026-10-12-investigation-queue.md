# Investigation Queue Implementation Plan

**Goal:** Turn the map's visible-area observations into a short, explainable list of places to inspect.

**Architecture:** Group already published satellite candidates by their 0.05-degree cell on the client. Keep the calculation pure and read-only; render up to five leads in the existing sidebar and use the existing record detail interaction for navigation. Data quality derives from the same snapshot manifest and source states as the map.

**Tech Stack:** JavaScript modules, MapLibre GL, Node test runner, existing Playwright browser check.

**Spec:** `docs/analysis-product-2026-10-12.md`

## Task 1: Lead selection

- [x] Add failing tests in `tests/js/area-analysis.test.mjs` for distinct-hour grouping, filters, and ordering.
- [x] Run the focused test and record the expected missing-export failure.
- [x] Implement `investigationLeads(snapshot, bounds, hours, now, source, limit)` in `public/area-analysis.mjs`.
- [x] Run focused and full JS tests.

## Task 2: Investigation flow

- [x] Add a browser assertion for a visible lead and its record navigation in `tests/browser/live-map.mjs`.
- [x] Add a local fixture browser check in `tests/browser/investigation-local.mjs` for navigation, mobile fit, and stale/partial state.
- [x] Add the lead section and translated copy in `public/index.html` and `public/map-state.mjs`.
- [x] Render the leads and connect each control to map centering and the existing record detail in `public/main.mjs`; style within `public/style.css`.
- [ ] Run the final JS, Python, local browser, and preview browser checks; report separately what could not be verified live.

## Review focus

Check that source failures and stale snapshots cannot make an empty queue sound like no fire, that ordering is not described as risk, and that map and list filters agree.
