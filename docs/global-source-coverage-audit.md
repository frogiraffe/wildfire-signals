# Global regional source evidence audit

This adds a **working, public map feature** in the existing Global Region Explorer for assessing what the current available public snapshot actually contains for a selected worldwide geodesic circle. The circle is deliberately not interpreted as a country or administrative boundary.

## User flow

1. Open the global map, choose `Use map center` or `Choose on map`, and set 25, 50, 100 or 250 km.
2. The selected circle continues to show the 6/24/72-hour candidate observations, sensor trend and evidence leads.
3. The **Regional source evidence** panel below shows each source's *declared capability*, its snapshot collection status, whether records were observed inside this circle, latest timestamp and whether the collector is currently stale/partial. Use the full reference/rights links in the card when auditing provenance.
4. Select **Export evidence JSON** to save the exact displayed region, selection time, snapshot timestamp, independently sourced counts and warnings. It can be reviewed or compared with later exports.

All region analysis is computed from the **already-fetched public `/api/snapshot` JSON**, client-side and without additional upstream, Cloudflare or rate-limited NASA requests. It uses the existing MapLibre region selection, sharing and i18n. No geocoding service or country polygon API is required.

## Source/capability registry

| Source | Collected here? | Capability description | Evidence semantics |
|---|---|---|---|
| VIIRS NOAA-20 | Yes | FIRMS world request | 0.05° candidate cell-hours, unconfirmed thermal detections |
| VIIRS NOAA-21 | Yes | FIRMS world request | Same independent sensor channel |
| NIFC WFIGS | Yes | US agency incident layer | Current agency incident IDs within selected circle |
| CWFIS | Yes | Canada agency incident layer | Current agency incident IDs within selected circle |
| US NWS grid forecasts | On demand | US-specific weather lookup | **Not sampled or monitored by public snapshot** |
| NIFC perimeter | On demand | US-specific incident perimeter lookup | **Not sampled or monitored by public snapshot** |

The fixed entries are provider **capabilities**, not a claim that any given circle has guaranteed data coverage. Other countries can still use the global location and candidate analysis features, while missing regional official incident confirmation is marked as **not established**, not as absence of incidents. No administrative border is inferred from latitude/longitude.

## Operational evidence quality

- Known source states are `complete`, `partial`, `failed` and `deferred`; sources not present are **unreported**, not complete by default.
- A complete request means the service returned successfully; it is not evidence that every satellite overpass or thermal detection was captured, or that the source's geographical coverage was exhaustive.
- A missing snapshot produces **unknown counts**, not zeros. A stale snapshot or truncated/partial response has an explicit visible warning.
- Agency counts belong to the current provider layer; they are not filtered to the satellite's 6/24/72-hour lookback. Their known timestamps are treated as evidence times, not extinguishment outcomes.
- Weather and perimeter capability rows explicitly say `not monitored here`: their individual on-demand requests are distinct from public collector health.
- All counts relate to the **selected circle**, not a verified national coverage percentage. Zero observed records does not establish no fire. Unknown labels/validation remain unknown.
- The exported JSON has `regionCoverageVerified=false`, `confirmedFireCoverageVerified=false` and `validNonFireLabelsAvailable=false`. It must not be used as an incident truth table or a model evaluation target.

## Development validation

```sh
npm run test:public
node tests/browser/investigation-local.mjs
```

The browser suite requires Playwright Chromium, installed by the dedicated GitHub Actions workflow. Tests exercise antimeridian, success/failure/deferred source semantics, unknown and stale snapshots, missing and zero-record distinctions, time ordering and late receipts, current-layer agency timestamps, HTML panel controls and a downloadable JSON audit on desktop and mobile.

## Next engineering work

This is deliberately a **snapshot-based operational coverage panel**, not country-by-country empirical acquisition completeness. Validated geographic percentages require a trusted country boundaries dataset, a source coverage manifest, independent sensor swath/orbit information, provider outage receipts and reproducible historical sampling denominators. Research archives and public snapshots can be linked in later releases to support that audit. Claims of worldwide forecasting remain unvalidated.
