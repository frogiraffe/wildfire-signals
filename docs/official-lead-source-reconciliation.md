# Direct official NIFC evidence re-verification for historical review leads

Previously the multi-year NIFC importer produced a versioned SQLite historical archive. Independent reviewer receipts permitted operators to save their own files with a hash, but **a checksum alone never authenticated the publisher**. This opt-in feature closes one specific provenance gap: it re-fetches a bounded number of those historical polygon leads **directly from the pinned official government ArcGIS HTTPS API**, verifies them against original queue source identities, and preserves the exact GeoJSON response bytes for later investigation.

## Usage

First use the established `perimeter_study sync` and `label_review prepare` commands. The latter must produce an original *unadjudicated* review queue containing NIFC source leads and optionally independent-frame controls.

Then execute:

```bash
python -m fire_public.official_lead_refresh \
  --queue /private/wildfire/unadjudicated-queue.json \
  --perimeter-db /private/wildfire/nifc-study.sqlite3 \
  --max-leads 8 \
  --json /private/wildfire/official-lead-reconciliation.json \
  --source-dir /private/wildfire/official-source-responses
```

The archive and original queue stay unchanged. The report and response directory must not exist beforehand; no existing file is overwritten.

## What is verified

The CLI:

1. Verifies the review queue's source years, recorded NIFC identity, original incident names, and exact underlying source batch identities against the old SQLite source archive. The historical study tool re-checks the selected source ObjectID list and full original feature SHA-256 checksums.
2. Queries the **fixed** NIFC FeatureServer layer metadata and fails if its official service-item ID, geometry and field contract no longer match expectations.
3. Issues read-only HTTPS `/query` requests for each year's selected ObjectIDs, with a 45-second timeout, no cross-host redirects and strict byte limit. No arbitrary user-entered URL is fetched.
4. Checks every returned GeoJSON polygon for the exact requested ID, source year, bounded WGS84 coordinate rings, and unchanged source GlobalID. Missing or mismatched source IDs **fail**; they never become verified "no-fire" cases.
5. Recalculates the original and current feature digests and classifies each verified lead as `same_content_as_archived` or `source_revision_since_archival`. A revision is a **source-record update**, not actual wildfire growth.
6. Preserves the **original raw response bytes** as `nifc-year-YYYY-response.geojson` plus a JSON report with exact response hashes and byte lengths, original queue SHA-256, source batch IDs, fetch date, layer schema SHA-256, transport status, provider rights and per-lead digest comparisons.

To keep government load bounded, the command refuses more than **16** source leads, default **8**, and generates at most one GeoJSON query per year. The maximum raw response is 8 MiB. The source provider metadata is also size-limited using the existing pinned source client.

## Scientific interpretation

`direct_pinned_official_https` means the program contacted the known NIFC service over an authenticated TLS connection **at the time of this verification**. It does not mean the government cryptographically signed a historic record, that the archive contains every fire, or that current records had been published before the historical event date.

Unlike manually supplied receipt files, the provenance of these latest response bytes comes directly from the fixed source endpoint. This is **official historical polygon source context only**. It does **not** prove independent ignition time, a complete outcome registry, fire absence, adjudicator independence, weather availability, scientific sampling completeness or model skill.

The original source lead evidence is **not** automatically inserted into the `label`/`primary`/`secondary`/`coverage` receipt slots or treated as independent outcome evidence. Human reviewers still need genuinely independent outcome and negative-registry coverage records for an evaluated cohort.

## Real-source CI integration

The preexisting multi-year live CI test already downloads eight genuine historical NIFC features and prepares an unadjudicated review queue. The same job now re-fetches each of those eight leads from the real official source, verifies the original identities, checks any revisions, and stores a new `official-lead-reconciliation.json` alongside the raw provider GeoJSON responses.

Its seven-day GitHub Actions artifact remains experimental public-source evidence. It does not contain genuine reviewers' private information or independently authenticated non-fire outcomes. The synthetic region-time frame controls are test scaffolding only.

Local offline unit tests inject source-shaped GeoJSON bytes (and clearly mark the transport as `injected_test_transport`), testing revision detection, missing IDs, identity drift, metadata spoofing, source queue tampering, strict limits and reproducible source-byte export. The actual government endpoint is tested separately by GitHub Actions, never claimed on the basis of fixtures alone.
