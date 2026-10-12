# Analysis product: from observations to investigation

Status: working plan, updated 12 October 2026. The public map is a preview, not a fire validation or forecasting product. The current collector has no weather source; the meteorological stage below is planned research and a bounded pilot, not shipped functionality.

## User job

For an area on the map, answer: **which recent satellite observations deserve a closer look, what evidence supports them, and what is missing?** A candidate remains a 0.05-degree cell-hour observation. Repeated observations are not proof of a wildfire, growth, severity, or a shared incident.

## Product contract

- The user's viewport, time window, and source filter define the investigation scope. The UI always states that this is a map viewport, not a country or administrative boundary.
- An investigation lead is one observed 0.05-degree cell, grouped across distinct UTC hours. Show its latest observation, number of distinct observed hours, sensor names, and a link to its latest underlying record. Put cells seen in multiple hours first, followed by recent single-hour cells. This is a navigation order, not a danger score.
- Limit the first release to five leads with an observation in the last 12 hours. When sources are incomplete or the public snapshot is stale, show that condition beside the leads. An empty list means no matching recent observations in the available data; it must not imply no fire.
- The map and lead list must use the same selected time window and source filter. Clicking a lead centers the map and opens the actual observation record.
- Do not merge nearby agency incidents into a verified wildfire. Existing 8 km links remain provisional.
- A news or social-media report must have a verified place, event time, fire type, and reuse permission before it can be compared with a satellite cell. A same-day report alone is not a match. For example, Quesería in Cuauhtémoc, Colima is around 455 km from the candidate at 20.025, -99.275; the [INEGI municipality bounds](https://www.inegi.org.mx/contenidos/app/mexicocifras/datos_geograficos/06/06005.pdf) place Quesería's municipality at 19°11′–19°30′ N, 103°29′–103°42′ W. A vehicle fire also does not establish a wildland fire.
- Weather is a separate **context layer**, not a fire-confirmation input. Every displayed value needs its source, valid time, model/observation type, grid resolution, and missing-data state. Wind direction and speed must be interpreted at the candidate's place and time; a broad forecast cell must not be presented as a measured local wind.

## Delivery sequence

1. **Investigation queue (current slice):** read-only, client-side grouping and ranked navigation within the visible map area; evidence and missing-data text; desktop/mobile checks. No new collection, KV write, paid service, or model.
2. **Cross-source evidence and regional history:** explicit area selection that survives map moves; coverage-aware hourly timeline; typed agency incident and independently sourced report links with spatial/time/type checks. Reject distant or mismatched examples such as the Quesería vehicle-fire report above. Requires historical storage, source licences, and Free quota review before implementation.
3. **Meteorological context pilot:** assess a globally available Free-compatible source and its rights, latency, spatial/temporal resolution, payload size, and reliability. Pilot 10 m wind speed/direction and gust, 2 m temperature and relative humidity, and recent precipitation for selected investigation areas. Separate observed/analysis fields from forecasts; do not make a request for each global candidate or write unbounded weather grids to KV. NOAA's [GFS/GDAS inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/) and [NOMADS subset access](https://nomads.ncep.noaa.gov/info.php?page=gribfilter) are candidates for evaluation, not an approved provider or a deployed integration. Show weather beside evidence with provenance; do not use it to declare fire or spread.
4. **Independent validation:** identify licensed, timestamped agency or perimeter ground truth by region; build a labeled evaluation set; measure matching sensitivity, false positives, and missingness. Europe/Türkiye official-feed research remains open. Evaluate whether weather adds measurable value rather than assuming it does.
5. **Decision support:** only after validation, test alert thresholds and prospective evaluation. Forecasting needs separate labels, baselines, calibration, and a measured utility criterion. Do not relabel collection, persistence, or wind direction as prediction.

## Acceptance for current slice

- Pure-function tests cover grouping by cell and distinct hour, filtering by viewport/time/source, antimeridian, ordering, and empty/stale/source-error states.
- Browser check verifies that selecting a lead moves to the corresponding observation and that desktop/mobile layout fits.
- Existing Python and JS suites pass. A successful preview check does not establish production deployment or scientific validity.
