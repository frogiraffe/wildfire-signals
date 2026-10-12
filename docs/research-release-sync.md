# Bounded GitHub Release sync → verified FIRMS SQLite archive → global coverage

This workflow completes the local research data pipeline built in PR #13. It lists this repository's public `analysis-evidence-YYYY-MM-DD` GitHub Releases, downloads the scan manifest and associated compressed pixel records into individually staged directories, verifies GitHub and source receipt SHA-256 hashes, atomically installs each complete daily release, imports them into SQLite, and produces a point-in-time satellite observation coverage report.

**This is a local opt-in command**. It does not enable `ENABLE_ANALYSIS_ARCHIVE`, create new GitHub releases, trigger the collector, issue new NASA FIRMS requests, run continuously or create an online database. If no eligible released research assets exist, no archived observations can be inferred. Public GitHub API reads have rate limits; setting `GITHUB_TOKEN` is optional and only changes public API authorization.

## Single command

Run from repository root (Python 3.12+):

```sh
python -m fire_public.release_sync \
  --assets-dir /private/wildfire-research/releases \
  --db /private/wildfire-research/firms-history.sqlite3 \
  --since 2026-10-01 \
  --max-releases 12 --max-total-mb 256 \
  --at 2026-10-12T18:00:00Z --hours 72 \
  --latitude 36.9 --longitude 30.7 --radius-km 100 \
  --coverage-json /private/wildfire-research/coverage.json
```

All of `--latitude`, `--longitude`, `--radius-km` are optional together; without them, coverage describes the locally archived worldwide pixels. Date `--at` defaults to present UTC. Do not write downloaded raw data, SQLite DBs, credentials or local analytics reports into the public Git repository.

## Download and verification

- Read only canonical GitHub API metadata for `frogiraffe/wildfire-signals`; consider a bounded number of pages, only non-draft research prereleases matching their exact dated tag.
- Select up to 30 latest eligible dates (8 by default), then process oldest to newest. Default 256 MiB compressed transfer limit, maximum 512 MiB per command, and per-asset 100 MiB cap.
- Accept exactly one timestamped `firms-pixel-scan-*.json.gz` plus zero to two timestamp-matched `firms-pixels-*.jsonl.gz` files. Reject unsupported assets, invalid names, missing SHA-256 digests, unexpected tag dates and non-canonical download URLs.
- Permit HTTPS downloads only from canonical repository release asset URLs, with redirects restricted to known GitHub release asset hosts.
- Stream downloads with hard size limits, then compare compressed-byte SHA-256 with both GitHub metadata and scan receipt manifest. Install a *whole release* only after checks pass, using a temporary directory and rename.
- Re-running the same dates verifies existing files without re-downloading them. Unexpected or corrupted local files stop the sync rather than being overwritten silently. Prior successfully installed daily directories are retained if a later download fails.
- Once downloads are verified, the existing `pixel_history.import_release_assets` validates raw CSV provenance and source times, rejects conflicting scans, maintains unique pixels and builds the SQLite research index. Repeated import is idempotent.

**Scope caveat:** Date-based pagination is capped, not exhaustive beyond the checked pages. When more than 500 entries must be considered, use smaller date windows or report incomplete release discovery. Successful import confirms consistency with published receipt/metadata, not independence of the provider or tamper-proof external truth.

## Output

The command prints structured JSON with `sync`, `import` and `coverage`, optionally writing the same JSON to a new file. This includes per-source scan availability and gaps, raw pixel detections, 0.05° UTC cell-hour groups, global circle selection and truncation indicators.

**Satellite pixels are thermal detections, not confirmed wildfires.** Source failure, an absent Release or zero candidate observations must never become negative training labels. Global geospatial querying does not mean worldwide independently validated fire identification.

## Test

```sh
python -m unittest discover -s tests -p 'test_release_sync.py' -v
python -m unittest discover -s tests -p 'test_pixel_history.py' -v
```

Tests simulate GitHub metadata/download transport while using real compressed research asset and scan file formats, full original PixelArchive generation, SQLite import and geographic as-of reporting. They cover idempotence, the international date line, bounded transfers, path/URL injection, corruption, absent files, malformed release metadata and complete chain execution.

## Pending steps

- Confirm the opt-in historical release publisher is enabled and that eligible daily Release assets actually exist; this code **does not enable it**.
- Provide resilient long-term backup of the local SQLite DB and raw Release files. Releases are repository/account dependent, not an independent preservation guarantee.
- Join the accumulated pixel archive into the existing historical evidence workbench with a strict first-captured-at contract. Expand global provider coverage with jurisdiction-specific sources and licensing.
