# Verified **live** NIFC ArcGIS API contract

Previous historical perimeter importer CI tests injected provider-shaped fixtures. They prove software behavior, **not** that the government endpoint responds with the same schema today. This extension adds a truly live provider compatibility test that queries the exact read-only US NIFC Interagency Fire Perimeter History FeatureServer layer.

Authoritative layer: https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0

Public source catalogue: https://www.arcgis.com/home/item.html?id=e02b85c0ea784ce7bd8add7ae3d293d0

## What is requested

The live test uses **only three bounded HTTPS GETs**, with no credentials, changes or collector integrations:

1. Fetch `f=json` metadata at the exact official layer URL, max 1 MiB and 30-second timeout. Verify the pinned service item ID, layer ID, polygon type, OBJECTID and GlobalID identity, official FIRE_YEAR_INT field, GeoJSON query capability and query permission. Keep the schema SHA-256 and minimal structural facts; do not publish unnecessary provider metadata.
2. Query year `FIRE_YEAR_INT=2018` for the official object ID list, bounded to 8 MiB and 45 seconds.
3. Query **one** polygon by a verified official object ID using `f=geojson`, `outFields=*` and EPSG:4326. The importer checks actual source year, original identity and geometry before saving it to ephemeral SQLite with the true 2026 capture time.

A source ID list may contain many official records, but the test only downloads **one polygon**. It is a **non-random sample**, not a statistical fire census. No query includes credentials, location tracking or privately owned data. All source requests are read-only and pinned to the official HTTPS layer; cross-host redirects are rejected.

## Run locally

```bash
python -m fire_public.official_live_probe \
  --db /private/wildfire/nifc-2018-sample.sqlite3 \
  --year 2018 \
  --output /private/wildfire/nifc-live-contract.json
```

The output is source-provenance and reproducibility evidence, including captured date/time, hashed official metadata and feature, source identity, archived source properties count, sample source area and explicit limitations. The SQLite file preserves the original verified geometry and attributes. It will not overwrite an existing report. The original perimeter importer remains suitable for intentional larger but bounded research imports.

GitHub Actions `Live official NIFC ArcGIS read-only contract verification` runs an offline regression job first and then makes the **real** source requests from GitHub's runner. Successful live proof writes `source-contract.json` into the short-lived `nifc-real-provider-contract` Actions artifact, retained for seven days, plus the check log. This is source integration proof, not a production weather or fire dataset. The artifact itself is not a long-term research repository.

## Science and provider boundary

- The official US IFPH layer contains retrospective historical wildfire perimeter records through 2019; it has agency-specific historical inclusion gaps. There are no defensible negative wildfire labels.
- A 2018 fire-year polygon first acquired in 2026 does **not** qualify as an input known to a predictor in 2018. As-of replay uses the actual local capture date.
- Original polygon areas/attributes are official source values; no geodesic acreage or wildfire evolution is derived.
- A successful three-request probe establishes temporary network/schema compatibility only. It does not establish completeness, data freshness, prediction validity or future API availability.
- If the live provider blocks a request or responds with incompatible metadata, the job must fail clearly; do not silently replace real responses with synthetic fixtures and still claim success.
