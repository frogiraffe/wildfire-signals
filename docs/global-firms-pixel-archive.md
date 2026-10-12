# Reproducible global FIRMS pixel research archive

Wildfire Signals can already produce opt-in bounded pixel-level NASA FIRMS research receipts from the existing Cloudflare/GitHub collector without additional FIRMS requests. The existing `fire_public.release_archive` publishes dated `analysis-evidence-YYYY-MM-DD` research GitHub Releases with compressed `firms-pixels-*.jsonl.gz` assets and one `firms-pixel-scan-*.json.gz` scan receipt. Those are **public, append-only research assets**, not verified wildfire incident observations or retrospective ground truth.

This feature closes the missing step: **verifiable, resumable local ingestion of these assets into a persistent queryable SQLite observation archive and a worldwide evidence coverage report.** No live collection, cloud usage, authentication, or model claims are changed.

## 1. Get a released daily asset set

In GitHub Releases for `frogiraffe/wildfire-signals`, find `analysis-evidence-YYYY-MM-DD` and download **all assets** belonging to the desired scan. Keep them grouped in a separate folder per release or scan. Directory recursion is supported.

**The opt-in production-side archive must actually have been enabled and produced a release.** Code being present is not proof that any usable data archive exists. GitHub Actions artifacts expire and are not a permanent archive; GitHub Releases store the opt-in research assets but are still dependent on repository/account availability. Back up locally if long-term retention matters.

Example local directory:

```
/private/wildfire-research/releases/
  analysis-evidence-2026-10-12/
    firms-pixel-scan-<UTC_STAMP>-<SHA16>.json.gz
    firms-pixels-<UTC_STAMP>-<SHA16>.jsonl.gz
```

The importer verifies:
- Scan receipt filename's compressed-byte SHA-256 prefix, UTC scan/capture times, schema, snapshot identity and exact two FIRMS source states.
- Declared pixel filenames, same scan timestamp, full gzip-file SHA-256, presence of **all and only** declared files in that scan's folder.
- Original source record SHA-256 based on canonical `source_fields`, `source_record_id`, pixel timestamp ordering, sensor names, coordinates, provenance/rights URLs and FRP units.
- Bounded compressed assets, compressed-scan decompression, per-line JSONL length and 250,000-row/file processing limit.
- Atomic multi-release import: one corrupted or conflicting scan rolls back the entire batch.
- Reimport of identical scan receipts is a no-op; repeated raw pixels remain unique by provider/source identity. Every unique pixel stores its **first scan and capture**, source read time, original source and licensing links and raw digest.

The original source files remain the reproducible evidence; SQLite is an index, not an unverified replacement for those files.

## 2. Import downloaded assets

```bash
python -m fire_public.pixel_history import \
  --assets /private/wildfire-research/releases \
  --db /private/wildfire-research/firms-pixels.sqlite3
```

This uses no internet access or secret keys. Put database and original downloaded files **outside this public Git repository**. Import writes only to the database path specified by the user.

## 3. Summarize historical evidence and coverage

```bash
python -m fire_public.pixel_history report \
  --db /private/wildfire-research/firms-pixels.sqlite3 \
  --at 2026-10-12T18:00:00Z --hours 72 \
  --latitude 36.9 --longitude 30.7 --radius-km 100 \
  --output /private/wildfire-research/antalya-coverage.json
```

The optional center/radius triplet may be omitted to summarize all archived pixels. Worldwide geodesic regions support longitude wrap across the antimeridian. The report uses **when source pixels were observed** and **when the scan was actually captured**; late observations do not appear in an earlier as-of reconstruction. A 168-hour maximum window limits query cost. The report counts raw pixel observations by source, **0.05° spatial cell × UTC-hour groups consistent with the public collector's aggregation**, repeated observed cells, source scan states and collection gaps over nine hours.

**Important:** The source archive retains raw VIIRS detection positions at their original precision. The report separately aggregates them to 0.05°/UTC-hour candidates; counts may differ from a particular hosted map snapshot because of the chosen archive set, source collection failures, retention windows and as-of capture cutoffs. Neither raw detections nor grouped cells are verified fires.

Every report marks `evidence_completeness: "unverified"`, `fire_confirmation: false`. A zero count or provider outage **never proves no fire**. The source states describe only scans actually present in the downloaded archive, not all historical collection attempts. Long gaps may reflect missing downloads, skipped collection, original upstream outages or disabled archiving. There is no global agency confirmation, weather, labels or trained model here. Report row caps (250,000 pixels/10,000 scans) expose truncation explicitly.

## 4. Verify

```bash
python -m unittest discover -s tests -p 'test_pixel_history.py' -v
python -m unittest discover -s tests -p 'test_release_archive.py' -v
```

Tests generate authentic `PixelArchive` gzip JSONL files and corresponding receipt schemas locally, including duplicate raw pixels across different scans, late capture exclusion, global dateline queries, failed sensor and zero-observation scans, tampering, conflicting scans, transactional rollback, idempotence and guarded report output.

## Next integration

The retained per-pixel archive and the existing agency `HistoryStore` remain separate by design. In later work, build a deterministic raw-pixel-to-0.05° cell-hour rollup and an explicitly provenance-labeled view that the historical workbench can consume. **Do not** join raw thermal detections to agency fire IDs purely by point proximity.
