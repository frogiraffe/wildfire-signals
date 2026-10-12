# Historical Workbench with official retrospective NIFC perimeters

This adds the missing last-mile linkage from **real-source bounded NIFC Interagency Fire Perimeter History GeoJSON** → versioned local SQLite → Historical Intelligence Workbench `report`/`compare`. It is distinct from the already integrated NIFC/CWFIS *active agency incident* records, FIRMS thermal pixels and NWS forecast receipts.

## Three steps

**1. Explicitly capture an official historical year sample:**

```sh
python -m fire_public.official_perimeters sync \
  --db /private/wildfire/ifph.sqlite3 --year 2018 --max-records 100
```

This command makes read-only US NIFC ArcGIS calls. It requires real internet access and provider availability, bounded to 100 records in the example. The archived capture timestamp is the time the application received the record; the historical source fire year **must not be treated as availability to a model in 2018**.

**2. Generate a unified historical evidence report:**

```sh
python -m fire_public.intelligence_workbench report \
  --db /private/wildfire/agency-history.sqlite3 \
  --pixel-db /private/wildfire/firms-pixels.sqlite3 \
  --perimeter-db /private/wildfire/ifph.sqlite3 \
  --perimeter-year 2018 \
  --at 2026-10-13T18:00:00Z \
  --latitude 37 --longitude -120 --radius-km 100 \
  --html /private/wildfire/reports/unified.html \
  --json /private/wildfire/reports/unified.json
```

`--pixel-db`, `--perimeter-db`, `--perimeter-year` and the entire location triplet are optional. An IFPH local geometry search is deliberately limited to circles of up to **250 km**; call `report` without a region for archive-wide research or use separate circles for larger geography.

The resulting HTML includes a dedicated **Official retrospective US fire perimeters** section showing source-year, captured source identities, actual capture timestamps, provider-reported acres, digest and known archive limitations. Detailed source polygons and full original properties stay in the official_perimeters read-only GeoJSON exporter, rather than bloating every intelligence report. Reports preview a maximum of 75 geometries and expose a truncation flag. No perimeter is joined to a FIRMS pixel or present-day incident using proximity.

**3. Compare retrospective source acquisition at two times:**

```sh
python -m fire_public.intelligence_workbench compare \
  --db /private/wildfire/agency-history.sqlite3 \
  --perimeter-db /private/wildfire/ifph.sqlite3 \
  --earlier-at 2026-10-12T00:00:00Z \
  --later-at 2026-10-13T18:00:00Z \
  --json /private/wildfire/reports/changes.json \
  --html /private/wildfire/reports/changes.html
```

The comparison distinguishes a polygon *first seen in the archive* and a *later revised polygon* based on its official identity and content SHA, without inferring actual ignition, spread, containment or extinguishment. The earliest year in the provider record is not when the application knew the perimeter.

## Crucial research boundaries

- The US retrospective IFPH archive is incomplete, principally pre-2020; it is **not** a global independently ascertained fire/non-fire dataset. Missing official geometries never become negative training examples.
- Counts from retrospective boundaries do not enter the active agency incident totals, FIRMS candidate totals, or weather observations. This prevents accidental double-counting.
- The source `GIS_ACRES` value is an official reported attribute, not a newly calculated polygon area or a time series of burned-area growth.
- The geometry search uses a bounded local projection approximation for user exploration, not a globally precise geodesic overlay statistic.
- Research perimeters captured today were not available as prospective inputs in earlier historical years. They could potentially inform a later properly designed outcomes study, but only with independent, licensed sources and a defensible negative sample protocol.
- The linked `--db` agency HistoryStore and optional `--pixel-db` and `--perimeter-db` are **three separate local archives** and should be backed up outside this public Git repo.
- Successful local tests do not establish that a live NIFC request has succeeded. The code has not been used to claim real predictive performance.

## Verification

```sh
python -m unittest discover -s tests -p 'test_workbench_official_perimeters.py' -v
python -m unittest discover -s tests -p 'test_official_perimeters.py' -v
```

The CI suite tests provider-shaped GeoJSON, real SQLite archive time consistency, prior source revisions, source/sample truncation, escaped HTML, CLI and export source protection, compatibility with existing research source classes and absence of implicit negative labels.
