# NIFC source-quality audit — real sampled historical perimeters

This implements a **source-integrity-checked, offline QA report** for the official historical NIFC research archive. It describes only the selected government's published and actually archived perimeter records, **not all historical wildfires in the United States**. A publication sample cannot establish verified fire-free locations.

## Run against already downloaded official records

First retrieve research perimeters using the established opt-in historical source command:

```bash
python -m fire_public.perimeter_study sync \
  --db /private/wildfire/nifc-study.sqlite3 \
  --year 2017 --year 2018 --records-per-year 12 \
  --seed wildfire-study-v1 \
  --report /private/wildfire/study.json \
  --geojson /private/wildfire/study.geojson
```

Next audit the **same local SQLite**, explicitly selecting the archive availability cutoff:

```bash
python -m fire_public.perimeter_quality \
  --db /private/wildfire/nifc-study.sqlite3 \
  --at 2026-10-13T18:00:00Z \
  --year 2017 --year 2018 \
  --json /private/wildfire/source-quality.json \
  --html /private/wildfire/source-quality.html
```

Neither QA command makes network requests. The year/capture-based `study_report` validates source batch counts, sampled original ObjectID SHA-256 and the full original feature SHA-256 against SQLite before a quality result is allowed. The latest archive batch known by the chosen `--at` cutoff is examined. An uncaptured year is **unknown**, not zero wildfires.

## Outputs and interpretation

For each year, the output exposes original source ObjectID population count, number sampled, source-record sample fraction, chosen batch/capture and selection provenance; plus:

- Nonempty **sample denominators and fractions** for `OBJECTID`, `GlobalID`, `FIRE_YEAR_INT`, `INCIDENT`, `GIS_ACRES` and optional `SOURCE` where present. All other observed nonempty attribute names are counted, to facilitate schema investigation without claiming stable columns across time.
- Flagged official source records for missing GlobalID/name/source/acreage, nonpositive reported acreage, obviously degenerate coordinate rings and longitude-wrap/wide extent manual review.
- Polygon/multipolygon geometry structure, sampled original positive `GIS_ACRES` median and vertex count median. GIS_ACRES is a **reported provider attribute**, not newly calculated or independently validated acreage.
- Matching original geometry SHA-256 across different source IDs and years as review candidates, **not automatically confirmed duplicates** or one event.
- An explicit scientific gate for additional **independent nonfire evidence**, region-time sampling, label censoring/source inclusion rules, feature issue-time and chronological/geographical evaluation. All `training_ready`, `forecast_skill_measured` and source census completeness claims remain false.

The report is self-contained JSON and escaped static HTML (no JavaScript), usable offline. It is an evidence quality audit rather than a reliable estimate of annual fire occurrence. For example, `GlobalID 3/4` means 3 of **4 sampled government polygons**, not 75% coverage of the nation's actual wildfire events.

Some official sources do not provide `SOURCE`; in that case the optional field is flagged for manual review, **not rejected**. Rings may be self-intersecting or otherwise topologically problematic even when nondegenerate; a GIS geometry validator such as GEOS/Shapely would be needed for a stronger topology audit. Source data can contain missing values without the fire event being invalid. Latitude/longitude screening and local degrees are not geodesic wildfire area.

## Real-provider CI

The existing bounded [multi-year live NIFC study workflow](../.github/workflows/test-perimeter-study.yml) now also runs the QA code against the **same eight real official records** already sampled from 2017 and 2018. This creates downloadable `quality.json` and `quality.html` alongside the existing genuine SQLite and GeoJSON. There are no added live NIFC HTTP requests, new paid resources, or Cloudflare deployments. Artifacts are retained for seven days, not a permanent archive.

Offline tests cover mixed historical-year source attributes, missing fields, zero acres, duplicate original shapes, suspicious degenerate rings, longitude wrap, as-of unknown years, tampered database checksums, source-name HTML escaping and immutable output paths.

**Not yet:** a nationally representative wildfire registry, verified nonfire negatives, fire ignition/containment outcomes, measurement of satellite detection accuracy, global ground-truth coverage or any scientifically validated fire forecast. Those require a dedicated independent target and sampling protocol.
