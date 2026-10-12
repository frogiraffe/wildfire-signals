# Analysis product: from observations to investigation

Status: working plan, 12 October 2026. The public map is a preview, not a fire validation or forecasting product.

## User job

For an area on the map, answer: **which recent satellite observations deserve a closer look, what evidence supports them, and what is missing?** A candidate remains a 0.05-degree cell-hour observation. Repeated observations are not proof of a wildfire, growth, severity, or a shared incident.

## Product contract

- The user's viewport, time window, and source filter define the investigation scope. The UI always states that this is a map viewport, not a country or administrative boundary.
- An investigation lead is one observed 0.05-degree cell, grouped across distinct UTC hours. Show its latest observation, number of distinct observed hours, sensor names, and a link to its latest underlying record. Put cells seen in multiple hours first, followed by recent single-hour cells. This is a navigation order, not a danger score.
- Limit the first release to five leads with an observation in the last 12 hours. When sources are incomplete or the public snapshot is stale, show that condition beside the leads. An empty list means no matching recent observations in the available data; it must not imply no fire.
- The map and lead list must use the same selected time window and source filter. Clicking a lead centers the map and opens the actual observation record.
- Do not merge nearby agency incidents into a verified wildfire. Existing 8 km links remain provisional.

## Delivery sequence

1. **Investigation queue (current slice):** read-only, client-side grouping and ranked navigation within the visible map area; evidence and missing-data text; desktop/mobile checks. No new collection, KV write, paid service, or model.
2. **Regional observation history:** explicit area selection that survives map moves, coverage-aware hourly timeline, a baseline matched to satellite sampling, and a clear distinction between changing detections and changing fire extent. Requires historical storage and Free quota review before implementation.
3. **Independent validation:** identify licensed, timestamped agency or perimeter ground truth by region; build a labeled evaluation set; measure matching sensitivity, false positives, and missingness. Europe/Türkiye official-feed research remains open.
4. **Decision support:** only after validation, test alert thresholds and prospective evaluation. Forecasting needs separate labels, baselines, calibration, and a measured utility criterion. Do not relabel collection or persistence as prediction.

## Acceptance for current slice

- Pure-function tests cover grouping by cell and distinct hour, filtering by viewport/time/source, antimeridian, ordering, and empty/stale/source-error states.
- Browser check verifies that selecting a lead moves to the corresponding observation and that desktop/mobile layout fits.
- Existing Python and JS suites pass. A successful preview check does not establish production deployment or scientific validity.
