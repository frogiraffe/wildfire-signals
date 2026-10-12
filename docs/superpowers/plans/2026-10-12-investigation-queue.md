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
- [x] Run the final JS (27/27), Python (40/40), and local desktop/mobile browser checks.
- [x] Deploy branch preview for code commit `2eee732` and run desktop/mobile browser check: [GitHub run 38186968423](https://github.com/frogiraffe/wildfire-signals/actions/runs/38186968423).

Code review found and the implementation fixed agency-only filter handling, combined stale/source warnings, and time rollover in an open tab. The preview test can pass when no recent lead exists; the local fixture test exercises lead selection and navigation. Mobile performance with a full global viewport remains to be measured before a stable release claim.

## Review focus

Check that source failures and stale snapshots cannot make an empty queue sound like no fire, that ordering is not described as risk, and that map and list filters agree.
