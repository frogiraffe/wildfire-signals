# Checkpointed thermal history in SQLite

`fire_public.historical_rollup` aggregates original, SHA-256 verified FIRMS pixel receipts already imported by `pixel_history`. It stays offline and uses the **same SQLite database**. The old 64-scan/1,000,000-pixel controls remain on the original in-memory exploratory model report; this command streams raw rows in batches of 2,000 and commits one scan at a time. It does not turn candidate gaps into no-fire observations.

```sh
python -m fire_public.historical_rollup \
  --pixel-db /private/firms-pixels.sqlite3 \
  --regions-json examples/batman-station-pilot-region.json \
  --start-date 2026-10-09 --end-date 2026-10-11 \
  --resolution hour --output-json /private/batman-hours.json
```

The region contract is hashed into a study ID. Each scan checkpoint stores receipt SHA-256, asset-manifest SHA-256, source states and unique raw/selected candidate counts. Raw source IDs are deduplicated by the existing importer; distinct 0.05° cell × UTC-hour candidates are deduplicated in the rollup. Observation and first-capture times remain separate. Query output includes original asset hashes, source URLs, rights URLs, provider counts and explicit unknown observation opportunity. Missing dates have no row and are never zero-filled. A study is queryable only when all known scans have committed. Query date ranges are limited to 366 inclusive UTC dates and regions to the existing nonoverlapping 12-circle contract.

An interrupted scan transaction rolls back, and the next command resumes at the last committed receipt. A source revision, newly discovered earlier scan or changed first-capture assignment requires `--rebuild`. Schema version 1 is checked; unsupported versions fail closed. Future semantic changes require a documented migration or rebuild from reverified originals. Keep both original hashed release assets and the SQLite database outside Git and back them up together. The compact aggregate cannot reconstruct missing original pixels. No automatic retention or backup service exists yet.

Run the synthetic scale benchmark outside Git:

```sh
python -m scripts.benchmark_historical_rollup \
  --db /private/rollup-scale-fixture.sqlite3 --rows 2000001
```

The final-code local 2,000,001-row fixture produced a 917,209,088-byte SQLite file. Two-scan and remaining three-scan processing took 4.596 s and 6.173 s; idempotent recheck 0.042 s; date/source-provenance query 0.067 s; peak process RSS 121,152 KiB. The 1,000,001-row fixture used 36,460 KiB peak RSS. These are **synthetic engineering rows**, not real fire or weather observations, and local one-run performance does not guarantee hosted cost. The real five-receipt/357,447-pixel archive processed in 1.986 s with 33,440 KiB peak RSS. No analytical DB is hosted in Cloudflare or Workers KV.
