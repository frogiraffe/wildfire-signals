# Official historical perimeter evidence — US NIFC IFPH

## What this adds

A real-source, opt-in research ingestion route for the **NIFC Interagency Fire Perimeter History (IFPH), All Years View**, published by the National Interagency Fire Center. The source is a retrospective US perimeter dataset **through 2019**, not a global live fire layer. The provider notes that historical perimeter information is incomplete and that collection rules differ by agency.

Official read-only ArcGIS FeatureServer layer:
https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0

Source catalogue and usage conditions:
https://data-nifc.opendata.arcgis.com/datasets/nifc::interagencyfireperimeterhistory-all-years-view/about

## Download an explicit research subset

```bash
python -m fire_public.official_perimeters sync \
  --db /private/wildfire/ifph-history.sqlite3 \
  --year 2018 --max-records 100
```

The program first queries the official source's year-filtered Object IDs, sorts them, then downloads up to the explicit maximum in batches of 25 through the official ArcGIS GeoJSON endpoint. All pages are checked for matching IDs, source year, finite coordinates, closed valid ring structure, reported area, geometry shape and duplicate records **before any rows are stored**. Per request: maximum 300 downloaded perimeters, 8 MiB JSON response, 50,000 vertices per polygon record, and 45-second timeout. There is no API key and no paid service. Network access is necessary **only for this explicit sync**; no data is downloaded by GitHub CI tests.

A chosen subset is biased toward lower Object IDs and **not** representative of all US wildfires. It is always marked with `subset_only` if fewer features than the service's reported IDs were downloaded. Even a complete ID list represents a provider-**incomplete** historical fire inventory.

SQLite stores original polygon GeoJSON, complete provider attributes, source-specific GlobalID/OBJECTID, the complete source-ID list digest, feature digest and actual *archive capture timestamp*. Source revisions are recorded as separate versions; no history is overwritten. Requesting fire year 2018 does not make the results historically available to the model in 2018.

## Report from the archive

```bash
python -m fire_public.official_perimeters report \
  --db /private/wildfire/ifph-history.sqlite3 \
  --at 2026-10-13T12:00:00Z --year 2018 \
  --latitude 37 --longitude -120 --radius-km 50 \
  --output /private/wildfire/reports/2018-nifc-evidence.json \
  --geojson /private/wildfire/reports/2018-nifc-evidence.geojson
```

`--latitude`, `--longitude` and `--radius-km` may be omitted together to export all archived geometries within the bounded report limit (500). The circular footprint search uses a local planar distance approximation, including longitude wrap across the international date line, with a **maximum 250 km radius**. It is a map/exploration filter rather than scientifically exact geodetic fire perimeter acreage or overlay area. Reported `GIS_ACRES` is merely the original provider value.

The static GeoJSON output can be loaded in QGIS, MapLibre or standard geospatial tools for source investigation. Output files are never overwritten, even with repeated commands. Database paths, downloaded records and local study reports should remain outside the public Git repository.

## Ground-truth and prediction limitation

- The polygon archive is **independent agency boundary evidence**, but not necessarily an independently adjudicated *event-occurrence binary cohort*. Some agencies omit smaller fires and historical years.
- A missing perimeter is **never** evidence of zero wildfires. No valid negative-label cases are created.
- The perimeter **source year** and any source metadata are distinct from the app's `captured_at`. Retrospective perimeters learned in 2026 are not valid prospective features for a 2018 prediction.
- The provider is US-only and through 2019; global live thermal candidate observations remain a separate source type. Do not automatically link a candidate cell to an agency fire by proximity.
- The collector is intentionally opted-in, bounded, and human-run; it does not alter live map collection, create subscription costs, enable an automated job or claim global modeling success.
- Source authenticity is limited to the TLS endpoint and response shape; unlike the independently downloaded FIRMS research artifacts, this API does not provide an externally signed immutable snapshot. Preserve the resulting SQLite and record digests for reproducibility.

## Verification

```bash
python -m unittest discover -s tests -p 'test_official_perimeters.py' -v
```

The CI suite uses a mocked official API transport (no remote fetch), but real GeoJSON, SQLite, as-of queries, revised provider geometries, dateline and polygon-hole checks, error rejection, CLI JSON/GeoJSON, and destructive-overwrite protections. **Real live NIFC API compatibility is a separate run** and is not implied by these tests.

Next worthwhile piece: integrate this distinct **retrospective perimeter evidence** alongside, not inside, active agency incidents and FIRMS counts in the Historical Intelligence Workbench. Then conduct scientific sampling/negative-label adjudication before running genuine performance studies.
