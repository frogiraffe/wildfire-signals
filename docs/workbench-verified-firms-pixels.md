# Verified FIRMS Release SQLite in Historical Intelligence Workbench

This completes the **research Release → local download → checksum-verified raw FIRMS SQLite → historical multi-source report → two-time Change Explorer** chain.

Use the established separate agency `HistoryStore` and the new raw pixel database together. Neither is a validated wildfire truth table.

## Complete practical sequence

1. Run opt-in hosted FIRMS research collection only if the project owner has authorized that deployment. Daily public research Releases must exist first; code alone does not guarantee this.
2. Download and import eligible releases with the documented bounded synchronizer:

```sh
python -m fire_public.release_sync \
  --assets-dir /private/wildfire/releases \
  --db /private/wildfire/firms-pixels.sqlite3 \
  --max-releases 12 --max-total-mb 256
```

3. Populate a separate local agency HistoryStore using the established checksum-verified `agency-*.json.gz` receipts or existing archival import. This is not performed automatically by the pixel importer.

4. Inspect archived agency identity and raw FIRMS evidence together at one decision time:

```sh
python -m fire_public.intelligence_workbench report \
  --db /private/wildfire/agency-history.sqlite3 \
  --pixel-db /private/wildfire/firms-pixels.sqlite3 \
  --at 2026-10-12T19:00:00Z \
  --latitude 36.9 --longitude 30.7 --radius-km 100 \
  --satellite-hours 72 \
  --html /private/wildfire/reports/antarctic.html \
  --json /private/wildfire/reports/historical.json
```

5. Compare two observed decision-time evidence states:

```sh
python -m fire_public.intelligence_workbench compare \
  --db /private/wildfire/agency-history.sqlite3 \
  --pixel-db /private/wildfire/firms-pixels.sqlite3 \
  --earlier-at 2026-10-11T12:00:00Z \
  --later-at 2026-10-12T19:00:00Z \
  --satellite-hours 72 \
  --html /private/wildfire/reports/changes.html
```

`--weather-db` is additionally available for archived US NWS forecasts. Weather and agency archives remain separate evidence kinds.

## Semantics and source health

- When `--pixel-db` is present, workbench **replaces** its satellite summary from the agency database with the verified raw-FIRMS-source summary. It never adds both independent summaries, preventing double counts of the same detections.
- The raw pixel count is labeled `raw_viirs_pixels`; the separate 0.05° cell-hour count uses the map's spatial/time binning. They have different denominators and must not be compared interchangeably.
- Scan receipt count, per-source succeeded/failed/deferred status, missing-scan gaps, pixel source memberships and query truncation are carried into the JSON and visible in the offline HTML.
- The report reads only source records captured by the requested date/time. It does not use future downloaded observations as retrospective evidence.
- Agency incidents retain their original provider identity. No thermal pixel is automatically promoted to an agency-verified incident, and satellite counts do **not** estimate confirmed wildfire count, burned area, spread, ignition risk or fire termination.
- The same `--pixel-db` must be used for both compared times. The pure comparison function explicitly rejects differing raw-versus-aggregate satellite evidence origins.
- No new upstream requests, Cloudflare writes, paid storage, autonomous permanent background collector or public model predictions are introduced.

Existing reports without `--pixel-db` continue using the original `HistoryStore` `satellite_candidate` path.

## Validation

```sh
python -m unittest discover -s tests -p 'test_workbench_pixel_integration.py' -v
python -m unittest discover -s tests -p 'test_change_explorer.py' -v
python -m unittest discover -s tests -p 'test_historical_context.py' -v
```

Tests build real gzipped pixel research manifests, import them with SQLite provenance safeguards and verify point-in-time reports, antimeridian inclusion, absence of double counts, separate agency identities, source observation availability, serializable CLI outputs and protection of the source pixel database.

**Not yet:** continuously populated, backed-up raw archive; independently labeled global wildfire truth; licensed worldwide weather feature coverage; prospective, geographically independent forecast validation. Data and computation are distinct from proven predictions.
