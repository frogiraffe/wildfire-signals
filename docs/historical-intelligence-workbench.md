# Historical Intelligence Workbench — offline agency evidence

This is a **local, read-only analysis/report interface** over an existing `HistoryStore` SQLite database, optionally populated with downloaded, checksum-verified prospective NIFC/CWFIS receipts. It does not require Cloudflare credentials, fetch any FIRMS data, change the public map or create a wildfire probability.

## Complete workflow

Download your own `agency-*.json.gz` research artifacts from the opted-in GitHub Actions receipt archive; keep the downloaded files outside the public repository. The prospective capture feature must actually be enabled and producing receipts: it is **not turned on by this implementation**.

Import the downloaded artifacts explicitly:

```bash
python -m fire_public.intelligence_workbench import \
  --db /private/research/history.sqlite3 \
  --receipts /private/downloaded-agency-receipts
```

The import uses the existing checksum, source-state, and duplicate-scan guards in `receipt_history.import_receipts`. Reimporting identical artifacts is idempotent. Failed/deferred sources do not turn carried forward rows into new agency evidence.

Generate self-contained reports at a chosen decision time:

```bash
python -m fire_public.intelligence_workbench report \
  --db /private/research/history.sqlite3 \
  --at 2026-10-12T15:00:00Z \
  --latitude 36.9 --longitude 30.7 --radius-km 100 \
  --limit 200 \
  --json /private/reports/antalya-evidence.json \
  --html /private/reports/antalya-evidence.html
```

Omit `--latitude`, `--longitude`, and `--radius-km` together to report all archived incidents, within a maximum of 500 displayed events. For other geographic selections, the worldwide search uses great-circle distance and supports the antimeridian. Existing archives may not have Turkish agency records: an empty result is a statement about **archived evidence**, never about fires being absent in Antalya.

**Never place the SQLite database, downloaded response artifacts or private generated report in the public Git repository.** Output files will not overwrite existing files unless `--overwrite` is specified; the source database cannot be used as an output path even with overwrite.

## What the report contains

- Decision-time UTC cutoff applied to both observed and actually captured timestamps.
- Archived agency identities and stable provider-specific event identifiers (never auto-linked to satellite cells).
- Current-as-of *source layer availability* from the most recent eligible complete/failed/deferred receipt, where the receipt tables exist.
- Reported agency status and event chronology with observed time **separate** from acquisition/capture time.
- Provider URLs, rights URLs in JSON, record IDs and hashes for audit and reproduction.
- Global search circle, missing coordinate counts, and result truncation flag.
- Receipt intervals longer than nine hours, source availability warnings, and a self-contained, HTML-escaped timeline report.

The HTML is static and script-free for offline viewing. The JSON report can be analyzed in Python or other tools.

## Known scientific limits

This is **not** a real-time fire dashboard, independent satellite confirmation, incident spread history, perimeter-growth calculation, occurrence-risk model or extinguishment prediction. An event not listed in a *complete* active source layer may have been corrected, archived, removed, or ended; the layer disappearance **does not establish that it was extinguished**. Failed/deferred sources convey missing coverage. Historical source timestamps do not show when data became available to the application; `captured_at` controls decision-time visibility.

Archived satellite thermal candidates stay separate from provider-defined wildland fire events. This report never converts missing thermal detections into valid negative labels. The experimental base-rate model remains separate and cannot be trained on these unverified agency-layer disappearances.

For real retrospective scientific modeling, acquire licensed, independently labeled positives and defensible negatives; add point-in-time weather, fuel and perimeter evidence, censoring policy and geographical/time holdouts. This workbench supplies traceable agency evidence and observability, not these outcome labels.

## Validation

```bash
python -m unittest discover -s tests -p 'test_intelligence_workbench.py' -v
python -m unittest discover -s tests -p 'test_receipt_history.py' -v
python -m unittest discover -s tests -p 'test_history.py' -v
```

Tests cover source failure versus non-listing, as-of replay, retroactively received evidence, geodesic selection, HTML injection safety, bounded outputs, CLI generation and non-destructive file handling.
