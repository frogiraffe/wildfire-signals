# Official MTBS reference acquisition and retrospective FIRMS comparison

The **MTBS Reference Fetch** tool connects the existing retrospective polygon–pixel benchmark to the publicly available USFS MTBS burned-area boundaries FeatureServer. It requests source-defined **wildfire** fire-type perimeters for a year, optionally restricted to a world-geographic box, verifies and safely saves a complete GeoJSON reference with a separate SHA-256 provenance manifest, then allows a checksum-bound pixel benchmark.

This is a **manual offline research workflow**; it does not change hosted collectors, add GitHub schedules, transmit private data, deploy a model or make any wildfire risk assertion. Fetching performs only bounded public HTTPS queries to one pinned USFS service; benchmark evaluation performs **no network calls**.

Official layer: https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/EDW_MTBS_v1/FeatureServer/0

The layer exposes `FIRE_ID`, `FIRE_NAME`, `FIRE_TYPE`, `IG_DATE`, `YEAR` and WGS84-exportable burned area polygons. It includes **post-event mapped boundaries**, not point-in-time fire observations. Government references can be edited/versioned; the metadata records when *this system* actually downloaded the file, not when the agency originally published each fire.

## 1. Acquire a small, explicitly bounded reference cohort

For example, request the 2024 MTBS layer for a western U.S. geographic bounding box. Coordinates are WGS84 **west south east north**, not a country/state boundary:

```bash
python -m fire_public.mtbs_reference_fetch \
  --year 2024 --bbox -124 32 -115 43 \
  --max-features 250 \
  --geojson /private/mtbs/mtbs-2024-west.geojson \
  --metadata /private/mtbs/mtbs-2024-west.metadata.json
```

The command saves both outputs only when *all source pages have been read* and the complete feature set fits the requested cap. Maximum 500 features, 100 per source request, 6 page requests per geographic selection, 8 MiB per response and 30 MiB assembled reference. No truncation or over-budget data is silently accepted. Requests are pinned to the official USFS service and redirects are rejected. Antimeridian-crossing selection boxes are split into two separately paginated envelopes; duplicate event IDs are checked for conflicts.

The metadata contains the official URL, exact query URLs, date/year/bounds, UTC retrieval time, full SHA-256 of the stored normalized GeoJSON and clear `source_publication_date_independently_verified: false` and `geographic_completeness_verified: false` declarations. This provides an audit trail for a given downloaded file, but **does not prove data accuracy or independent agency source authenticity**.

Large area/year requests can exceed the cap; narrow the bounding box and re-run to obtain complete smaller cohorts. The tool never modifies existing reference files.

## 2. Run retrospective comparison against FIRMS pixels

The downloaded provenance manifest can now be given directly to the benchmark; the runner verifies its SHA-256 and uses the conservative recorded retrieval time as a lower bound on when the reference was actually accessible to this workflow.

```bash
python -m fire_public.perimeter_benchmark \
  --pixel-db /private/wildfire/firms-pixels.sqlite3 \
  --geojson /private/mtbs/mtbs-2024-west.geojson \
  --reference-manifest /private/mtbs/mtbs-2024-west.metadata.json \
  --as-of 2026-10-12T22:00:00Z \
  --observation-days 14 \
  --json /private/mtbs/benchmark.json \
  --html /private/mtbs/benchmark.html
```

Change `--as-of` to a time **after the actual download timestamp recorded in metadata**. If the date is before retrieval, the evaluator refuses to use future reference data. It will also refuse a changed GeoJSON whose hash disagrees with the metadata.

The reference cohort represents only large mapped wildfire boundaries **from MTBS geography and fire-type definitions**. It cannot establish the correctness of wildfire detections outside those polygons or outside that agency's published scope. The final perimeter is known only retrospectively.

**Historical data overlap remains a genuine blocker for empirical numbers.** The project's new research Release importer starts at the dates actually collected; there is no silent historical backfill. If local FIRMS history does not cover the selected historical fires, the report correctly marks unassessed/no receipt rather than treating it as a failed prediction or no-fire truth.

## Validation

```bash
python -m unittest discover -s tests -p 'test_mtbs_reference_fetch.py' -v
python -m unittest discover -s tests -p 'test_perimeter_benchmark.py' -v
```

The acquisition suite uses an offline simulated ArcGIS transport with the real query URLs and actual GeoJSON schema, and tests pagination, source limits, bbox antimeridian, mismatched/manipulated downloaded reference, provenance manifest binding, CLI consumption, trusted endpoint restrictions and preflight output safety. These tests do not assert that live MTBS downloads succeed at all times or that any model has a real detection score.
