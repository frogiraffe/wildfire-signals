# Historical Change Explorer: compare two decision-time evidence states

The `Historical Change Explorer` reuses the existing SQLite historical archive, provenanced NIFC/CWFIS agency receipts, archived FIRMS thermal candidate observations, and optional captured NWS forecasts. It answers **what new evidence was available to this archive between two decisions**, not whether a fire ignited, grew, was contained or extinguished.

## Offline CLI

Use an existing research archive containing actual downloaded receipts, or a locally constructed HistoryStore. Keep private archive files outside the Git repository.

```bash
python -m fire_public.intelligence_workbench compare \
  --db /private/research/history.sqlite3 \
  --weather-db /private/research/nws-weather.sqlite3 \
  --earlier-at 2026-10-10T00:00:00Z \
  --later-at 2026-10-12T00:00:00Z \
  --latitude 36.9 --longitude 30.7 --radius-km 100 \
  --satellite-hours 72 \
  --json /private/reports/changes.json \
  --html /private/reports/changes.html
```

`--weather-db` and the entire latitude/longitude/radius triplet are optional. Omit the location triplet to compare all events in the local archive. Each as-of report is rebuilt independently using the same scope and 6/24/72-hour satellite window.

The `report` subcommand remains unchanged. Both `report` and `compare` refuse to overwrite existing outputs without `--overwrite`, and will never overwrite the source SQLite archives even with that flag.

## Evidence changes, not inferred outcomes

- **Agency events:** compared by stable provider-specific `event_id`, never by spatial proximity. Newly known identities are classified as `first_seen_in_archive`, not `new_ignition`. Source-reported changes are explicitly separated from changes in agency layer availability, and both are distinguished from merely added archived observations.
- **Missing agency records:** if an event disappears from a complete active source, the output is `not_listed_in_latest_complete_scan`, not `extinguished`; if a provider fails, its status is `source_unavailable`. Neither is a negative or outcome label.
- **Satellite candidates:** counts show separate rolling windows of unverified thermal candidates, distinct cells and recurrent cells. Their difference is not burned-area growth or fire progression. Individual candidates are not assigned to an agency fire.
- **Weather:** if two saved NWS grid forecast receipts differ, the report notes which receipts were available and when; changed forecasts are not measured on-site weather changes. Outside US NWS coverage, missing weather is explicitly missing, not a numerical zero.
- **Truncation:** reports expose any display, satellite row, agency evidence timeline or weather query caps. `comparison_untruncated` means only that these caps were not hit — never that the underlying monitoring history is complete.

The HTML output is responsive, standalone, escaped, and script-free, suitable for local inspection; the JSON preserves machine-readable evidence changes and their provenance hashes. No network calls, new keys, provider spending, data collection changes or public predictions occur.

## Test contract

```bash
python -m unittest discover -s tests -p 'test_change_explorer.py' -v
```

The integration suite creates genuine receipt-format fixture archives and imports them into real SQLite tables. It covers source-reported OC→UC/BH changes, failed providers, non-listing in complete scans, new archive identities, late satellite receipt exclusion, globe selection, bounded comparisons, XSS-safe static HTML and CLI overwrite protection. Fixtures are demonstrations of software behavior, **not real model skill or global detection accuracy**.

Future expansion: independently observed incident geometries and verified outcomes, a historical provider coverage registry, quality-audited global weather sources, and real-label spatial/temporal evaluation. A comparison report is not evidence those prerequisites are complete.
