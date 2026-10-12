# Real official NIFC multi-year sample and source-coverage audit

This adds a reproducible, opt-in way to collect **actual government-published wildfire perimeter polygons across several historical years**, rather than continuously validating only one low-numbered ObjectID. The endpoint is the pre-existing read-only [NIFC IFPH historical FeatureServer](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0).

## Collect a multi-year sample

```bash
python -m fire_public.perimeter_study sync \
  --db /private/wildfire/nifc-study.sqlite3 \
  --year 2013 --year 2015 --year 2017 --year 2018 \
  --records-per-year 20 \
  --seed reproducible-study-v1 \
  --report /private/wildfire/nifc-multi-year-summary.json \
  --geojson /private/wildfire/nifc-multi-year.geojson
```

This first reads the source Object ID list in each chosen year and hashes `seed:year:objectId` with SHA-256. It downloads the lowest-ranked IDs using the existing, bounded NIFC GeoJSON importer; in contrast, the original `official_perimeters sync` default selects the first sorted IDs. The hashed method gives each published source ID an equal selection rank under an ideal hash, **but does not correct missing official fire records, nonrandom reporting, regional source gaps, or other sampling biases**. This is an *unweighted exploratory sample of records found by the source*, not a fire-event probability sample of the whole United States.

Maximum one run: eight distinct years (through 2019), 30 records per year, 240 total polygons. Each official year costs one read-only ID request plus one or two bounded geometry requests. No scheduled continuous collection, new paid services, secret keys, live map modification or fire-probability features are introduced.

Each year preserves its official source total, the full source-ID list SHA-256, selected-ID list SHA-256, deterministic seed and sampling mode, original provider polygons and attributes, per-feature SHA-256 and the **actual capture timestamp** in SQLite. Later independently captured agency revisions remain versioned.

The report includes per-year source record counts, selected polygon counts, selection fractions, availability and completeness warnings, polygon geometry types, original attribute availability and descriptive provider-reported acreage summaries. **Comparing totals between years is not measuring wildfire frequency** because reporting practices and inclusion differ.

## Reproduce results entirely offline

```bash
python -m fire_public.perimeter_study report \
  --db /private/wildfire/nifc-study.sqlite3 \
  --year 2013 --year 2015 --year 2017 --year 2018 \
  --at 2026-10-13T18:00:00Z \
  --report /private/wildfire/nifc-replayed.json \
  --geojson /private/wildfire/nifc-replayed.geojson
```

Only snapshots actually captured before or at `--at` can appear. If a requested year was not archived by that moment, the JSON reports `not_captured_by_decision`, **not zero fires**. The sample report never invents valid negative labels and is not eligible as a prospective 2013–2018 model feature.

When run against an archive with repeated captures, offline `report` selects the latest eligible full batch for each year. Live `sync` pins the exact batch ID of each year's downloaded record set to avoid ambiguity if more than one study uses the same capture timestamp. Polygon content and selected original IDs are re-verified against SHA-256 on each report.

The geoJSON export includes original NIFC polygon geometry and source attributes for GIS investigation. Reports refuse to overwrite existing files or the source SQLite. Keep real data and local backups **outside this public source repository**.

## Verified real-provider sample in CI

The [NIFC multi-year Actions workflow](../.github/workflows/test-perimeter-study.yml) first executes provider-shaped offline validation tests, then makes bounded **real** NIFC requests for four records in 2017 and four in 2018. It verifies source totals, exact original polygons, recorded capture time and lack of negative labels, and makes the resulting SQLite + GeoJSON + JSON study report downloadable as a seven-day GitHub Actions artifact.

CI success establishes current endpoint compatibility and eight actual published perimeters. **It does not prove government records are exhaustive, establish global coverage, construct valid nonfire negatives or give a model Brier score.** Those require independent study design and a separately audited sampling denominator.

## Future use

The unified Historical Intelligence Workbench already reads the same official perimeter SQLite using `--perimeter-db`. Following the real-source audit, useful next stages are (1) source-year consistency/quality checks and explicit geographic availability registries, (2) a defensible *independent* negative sampling frame, and then (3) a declared target and prospective feature audit. More polygons by themselves are not a defensible fire prediction dataset.
