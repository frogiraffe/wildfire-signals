# Analysis Engine v1: regional thermal signal statistics (worldwide)

**Delivered maturity:** descriptive observational analysis from the current public NASA FIRMS snapshot. It runs directly in the existing worldwide map: choose any point, radius (25/50/100/250 km), 6/24/72-hour window and All/VIIRS source, then inspect the **Statistical signal analysis** panel. Export its self-contained provenance/quality/metrics JSON. This is a real analytical function, not another source-archive feature or a synthetic model accuracy demonstration.

## Statistical target and units

The empirical unit is a **distinct NASA VIIRS thermal candidate in one collector 0.05° cell and one UTC hour**, *not* an individual burned area, fire incident, land-hectare or satellite overpass. The source collector groups raw pixels into these cells/hours. The analysis deduplicates repeated records and merges source membership per cell-hour using the same UTC timestamp floor, including 180° / −180° normalization. The circular region uses WGS84 coordinates and geodesic great-circle distances, not a country whitelist. Only events observed and received at/before the snapshot scan (and within the selected analysis decision-time window) are considered.

For a selected equal-duration window, output:

| Metric | Meaning | Scope |
| --- | --- | --- |
| Cell-hours | Number of distinct in-window thermal cell/hours | Not the number of fires or fire events |
| Distinct cells | Count of 0.05° cells with at least one candidate | Not a size/burned area estimate |
| Recurrent cells | Cells with observations in 2+ different UTC hours | Not proof of a continuous physical fire |
| Recurrent cell-hours | Total cell-hours in recurring cells | Can include non-adjacent hours |
| Consecutive transitions | Within-cell observed UTC-hour pairs h−1 → h | Satellite passes between hours are not guaranteed |
| Two-sensor cell-hours | Cell-hours recorded under both NOAA-20 and NOAA-21 | Co-membership, **not** independent wildfire confirmation |
| Six UTC time bins | Count, unique cells and per-sensor memberships in six equal-duration UTC bins | The acquisition denominator is unknown |
| Median and MAD | Median cell-hours per bin and median absolute deviation | Descriptive dispersion, no significance testing |
| Later minus earlier | Count difference between the second and first three equal-duration bins | Not a rate ratio or causal/weather effect |
| Later/earlier ratio | Defined only if the first-half count is nonzero | Not a wildfire risk ratio |
| Theil–Sen slope | Median of 15 pairwise cell-hour/bin slopes in units of cell-hours/hour | **Observed-record trend only**; no p-value or incidence inference |

The response includes the full time-bin data, per-source data, the source coverage audit, original scan time, source completeness, freshness/truncation flags, explicit limits, and **null** for verified fire counts, fire probability, wildfire spread, burned area and any hypothesis p-value. It does not fabricate satellite-overpass denominators or uncertainty intervals.

## Source/measurement quality gates

- **Unavailable scan**: numeric metrics and bins are `null`, not zero; no region count is asserted.
- **Source failed/deferred, collection partial, or snapshot truncated**: observed candidate statistics are still reported as *incomplete descriptive subsets*. Missing source hours are not set to zero observations. Source audit and limitations are exported alongside them.
- **Stale scan (>90 minutes)**: results are shown as stale, not as contemporaneous evidence.
- **Missing candidate rows under an otherwise current scan**: zero observed candidate cell-hours means **no candidate in the available snapshot only**, not no wildfire.
- **Agency-only source filter**: UI explicitly warns it is unsupported for thermal statistics; it does not substitute a fake zero.
- **Sensor co-membership**: NOAA-20/21 memberships are observations, not independent ground truth about event identity.

## What comes next

This first slice is intentionally bounded to the current 72-hour snapshot. A reproducible historical analysis requires longitudinal FIRMS original pixel releases plus capture-time/source-coverage manifests; the current map alone cannot establish acquisition exposure, forecast validity, independent ignition/outcome labels or geography-time holdout performance. The next research/implementation slice should validate *observation availability* and build correct denominators before wildfire incidence/ignition probability, followed by event-level labels and leak-free temporal/geographical backtests.

## Run

```sh
npm run test:public
node tests/browser/investigation-local.mjs
```

JavaScript unit fixtures test dateline boundaries, duplicate source/cell-hour records, correct sensor memberships, robust statistics, 6/24/72-hour gates, future acquisitions, stale/truncated/failed sources and absent fire-label assertions. Browser tests exercise the real regional selector and JSON export on both desktop and mobile viewports. The UI has Turkish and English translations. **No paid service, credential or new API** is introduced.
