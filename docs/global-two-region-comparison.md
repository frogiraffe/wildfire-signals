# Two-region worldwide satellite evidence comparison

A public-map **descriptive** feature for comparing satellite thermal **candidate cell-hours** in any two circles worldwide. This is not a wildfire likelihood forecast, event occurrence rate or comparative fire risk assessment.

## Using the map

1. Under **Global region explorer**, choose region **A** by clicking the map or using its center. Select a 25/50/100/250 km radius and a 6/24/72-hour satellite observation window.
2. Under **Compare two regions**, choose region **B** using the second map-picking control or the map center. The map draws distinguishable, antimeridian-safe outlines. Both circles share the exact same selected radius, source filter, UTC window and snapshot.
3. Compare candidate cell-hours and observed sensor memberships, inspect source freshness warnings and any overlap notice, then export `wildfire-two-region-comparison.json`. The link's `rlat`, `rlon`, `rr`, `clat` and `clon` parameters preserve the comparison.

There are **no hardcoded country restrictions**. A satellite source may be global while national agencies, weather grids and verified outcomes remain geographically bounded. The UI is translated into English and Turkish.

## Evidence contract and limitations

`public/region-compare.mjs` is a pure calculation consuming the same public snapshot used by the map and `regionCoverageAudit`. Equal radius and observation window prevent some trivial analytical mismatches; they **cannot** establish equal satellite acquisition opportunity, completeness, comparable land fractions or equal detection performance. The resulting difference is an integer in **0.05-degree aggregated cell-hours**; it must never be described as the difference in wildfires, burned area, active-fire severity or forecast probability.

The report explicitly records:
- both source-quality states, which original source scan each analysis is bounded by, its UTC time window, sensor memberships, and source coverage declarations;
- whether regions overlap (so the same observations may be counted twice);
- whether snapshot collection is stale, partial, unavailable or truncated;
- when an agency-only filter makes satellite comparison unavailable (instead of falsely showing zero fire observations);
- `wildfireRiskRankingAvailable: false`, `fireAbsenceInEitherRegionVerified: false`, `comparableAcquisitionCoverageVerified: false`, and `independentlyVerifiedFireDifference: null`.

A blank candidate circle means **no reported observation within the available snapshot** and says nothing about absence of wildfire. No data are written to source archives and no external APIs or paid resources are added.

## Tests

```sh
node --test tests/js/region-compare.test.mjs
node tests/browser/investigation-local.mjs
```

CI runs the entire public JavaScript suite and the local desktop/mobile Chromium scenario, including antimeridian geometry, source filter, overlapping region qualification, stale/partial/truncated evidence, geo-URL round trip and export guardrails.
