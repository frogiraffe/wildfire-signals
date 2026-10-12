# Experimental positive-only MTBS perimeter comparison

This is a **real-data-capable, offline retrospective overlap evaluator**. It compares historically archived, checksum-verified NASA FIRMS raw VIIRS pixels in `fire_public.pixel_history` against downloaded, externally published burned-area polygons, with explicit observation/capture/reference times and source provenance.

It is **not** a model, an independent satellite detection accuracy study, a validated wildfire classifier, or a spread simulator. It creates zero false-positive/true-negative labels.

## Real independent reference: USGS/USFS MTBS

An established government dataset is [Monitoring Trends in Burn Severity (MTBS)](https://www.mtbs.gov/), published through [USGS](https://www.usgs.gov/data/monitoring-trends-burn-severity-ver-120-april-2025) and official [USFS ArcGIS MTBS FeatureServer](https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/EDW_MTBS_v1/FeatureServer/0). It covers selected **large** fires, including prescribed fire and other burn types, in CONUS, Alaska, Hawaii and Puerto Rico. Small incidents, unobservable events and other nations are not fully represented.

The ArcGIS feature layer exposes `FIRE_ID`, `FIRE_NAME`, `FIRE_TYPE`, `IG_DATE` and polygons; older MTBS exports may use `Event_ID`, `Incid_Name` and `Incid_Type`. This program recognizes either case-insensitively, handles millisecond Unix epoch ignition dates, and falls back to `YEAR`/`STARTMONTH`/`STARTDAY` fields. Only explicit `Wildfire` / `WF` classifications are included. Prescribed, unknown and other types are **excluded**, not silently reinterpreted as wildfire.

**Preparation:** obtain a reasonably small WGS84 **GeoJSON** `FeatureCollection` from the official service's export interface (or GIS tool), with its polygons and source attributes. The source's native reference may be NAD83; export or reproject explicitly to GeoJSON longitude/latitude coordinates. Filter to at most 500 features and keep the original downloaded file plus its license/terms outside this public repository. This program requires an explicit HTTPS reference source URL; it hashes the bytes but **does not cryptographically authenticate the asserted publisher**, and reports this limitation.

MTBS final burned-area boundaries are **post-fire** outlines. They are valid only as retrospective spatial comparison geometry, never as information available when predicting ignition or future fire spread. No automatic fire association by vicinity is implemented.

## Prerequisite: an overlapping historical FIRMS dataset

The verified FIRMS research Releases introduced in this project started in October 2026. Existing MTBS MTBS public layers may presently cover **1984–2024**, so the datasets might have **zero overlap**. A meaningful real comparison requires independent archived FIRMS raw pixel records for the same event dates, e.g. from separately obtained, source-authorized historical NASA FIRMS downloads imported with provenance. The current research Release sync **does not** backfill 2024 or earlier observations. Running this CLI on a nonoverlapping archive should explicitly yield unassessed references or no intersections; neither constitutes evidence of model failure or wildfire absence.

## Offline usage

```bash
python -m fire_public.perimeter_benchmark \
  --pixel-db /private/wildfire/firms-pixels.sqlite3 \
  --geojson /private/reference/mtbs-2024.geojson \
  --source-url 'https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/EDW_MTBS_v1/FeatureServer/0' \
  --reference-published-at 2026-10-01T00:00:00Z \
  --as-of 2026-10-12T18:00:00Z \
  --observation-days 14 \
  --json /private/results/retrospective-mtbs.json \
  --html /private/results/retrospective-mtbs.html
```

The `--reference-published-at` argument must be based on the actual reference dataset's publication/release/version metadata; the example date is **illustrative**, not an independently confirmed publication timestamp. The program refuses references published after `--as-of`.

`--observation-days` must be 1–30 and defines a fixed, **research-selected** window from the reported incident ignition; it is not a source-confirmed fire duration. Fire references whose selected window has not ended by `--as-of` are excluded. FIRMS observations must fall in that window, be present in the archive, and have a first-captured timestamp no later than the evaluation cutoff. No later-collected pixels appear in an earlier as-of analysis.

## Method and outputs

- Spatial test: raw pixel coordinates intersect the final GeoJSON polygon, with MultiPolygon, interior hole and antimeridian support.
- An archive record has its own source identity and observed/captured times. Overlapping reference polygons may independently count the same pixel; counts are *polygon overlaps*, not deduplicated wildfire incidents.
- Source receipt evidence by event window: which FIRMS sensor scans were recorded, complete/failed/deferred collection states, whether any scan existed. A successful scan **does not certify orbital satellite acquisition completeness**.
- Event outcomes: `intersection_observed`, `no_intersection_in_archived_pixels`, and `unassessed_no_collector_evidence`. The last two are **not** valid negative wildfire labels.
- The displayed positive-only fraction is `reference_overlap_fraction_given_some_receipts` — references with at least one within-perimeter archived pixel divided by references with any captured collection scan. **This must never be described as recall, sensitivity or validated detection accuracy.**
- Explicit evidence and data bounds: max 30 MiB GeoJSON, 500 reference features, 50,000 polygon vertices/event, 100,000 raw pixel rows/event, 10,000 scan receipts/event and 300,000 total pixel-polygon associations. Oversized queries fail rather than silently return deceptively complete scores.
- The JSON report includes reference file SHA-256, provenance URL, publication time, retrospective label semantics, sensor counts, per-event first observation/capture, collection limitations and `valid_negative_labels_created: 0`.
- The HTML is a portable, script-free, escaped report usable offline.

### Validation

```bash
python -m unittest discover -s tests -p 'test_perimeter_benchmark.py' -v
python -m unittest discover -s tests -p 'test_pixel_history.py' -v
```

Tests create authentic locally signed PixelArchive gzip receipts, import them with the real SQLite indexer and query retrospective GeoJSON features. They verify source type exclusion (prescribed fire), 2-source pixel overlap, multiple polygons and holes, international date line, lack of evidence vs zero, future publication leakage, incomplete provider scans, protected output files and malicious HTML escaping. Fixtures demonstrate program behavior only — no empirical wildfire accuracy is claimed.

## What would be needed for proper real-model validation?

Reliable historical sensor coverage denominators, independently labeled fire and defensible non-fire outcomes, matched temporal windows, source availability and time of publication for all features, region/event temporal holdouts, false-positive sampling design, probability calibration and external geographic validation. For countries beyond MTBS jurisdiction use appropriately licensed independent agency perimeter sources rather than generalizing US scores globally.
