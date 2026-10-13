# Offline prospective agency incident time machine

This experimental **local research application** replays previously captured agency incident records at a selected decision time. It is a *different tool from the live map*: its source is a verified local SQLite archive of genuine prospective NIFC/CWFIS agency receipt files. It **does not** infer or confirm a wildfire physical identity from the agency ID, absence from a current layer, or nearby satellite signals.

## Full data-to-product workflow

An eligible normal collection job generates bounded, optional `agency-*.json.gz` artifacts when `ENABLE_ANALYSIS_ARCHIVE=true`. As of this commit, automatic receipts remain opt-in and are retained as GitHub Actions artifacts for up to 90 days; a durable archival solution is still needed. Users must **download** their permitted receipt files and store them locally before they expire. This new feature does not enable scheduled collection, bypass account permissions or publish private evidence.

Use [prospective agency receipt import](prospective-agency-receipts-2026-10-12.md) to verify and add multiple receipt batches into a local SQLite database **outside the repository**:

```sh
python -m fire_public.receipt_history \
  --db /private/agency-history.sqlite3 \
  --receipts /private/downloaded-agency-receipts
```

Then generate a private, self-contained event investigation interface from the **already imported** database:

```sh
python -m fire_public.prospective_replay \
  --db /private/agency-history.sqlite3 \
  --provider cwfis \
  --output-dir /private/agency-time-machine-001
```

Open `/private/agency-time-machine-001/index.html` locally in a browser. Select a **captured decision time**, search source identifiers and names that were *already known* at that time, open a source event, and inspect the original chronological receipt entries. The button exports only the selected as-of event evidence, preserving the source provenance and explicit absence of fire labels.

To replay before a fixed cutoff or keep a large archive within the safety bounds, add `--at 2026-10-12T15:00:00Z` and/or `--official-id CA-1` (requires `--provider`). With no `--at`, the latest actual imported receipt time is used, **not the current wall clock**.

Artifacts are created new-only with directory mode `0700`, file mode `0600`; no existing output is overwritten. The source DB is opened read-only (no migration). The HTML has all code/data embedded, no network, a hashed CSP and an explicit, bounded JSON export. Keep both HTML and JSON outputs private; **do not upload them to GitHub or deploy to the public Pages site**.

## Scientific interpretation

For each agency ID, every imported receipt is represented separately:

| State | Meaning |
| --- | --- |
| `listed` | A *complete* provider request included this agency's source ID. The status is the provider's literal code. |
| `source_unavailable` | Provider fetch failed or was deferred; old rows visible in a snapshot are not a new official confirmation. |
| `not_listed_in_complete_scan` | A complete request's current provider layer did not list the source ID. **Not an extinguishment, nonfire control, or negative event label.** |

All time controls use original `captured_at`, not only `modified_at`; a source record published earlier but captured later is **not available to the earlier decision point**. CWFIS stage-of-control reversal is not an independent extinguishment label. NIFC and CWFIS event IDs are kept **distinct**; no match is inferred from shared names or spatial proximity. This scoped US/Canada input **does not restrict** the planned global source provider architecture.

Tests cover mixed complete/failed/deferred source runs, status updates and returns, absence without false negatives, same original record replay, incorrect missing source observations, mutation/tampering, decision-time name leakage, privacy boundaries and fully offline browser behaviour.

## Verification

```sh
python -m unittest discover -s tests -p 'test_prospective_replay.py' -v
node --test tests/js/prospective-replay.test.mjs
node tests/browser/prospective-replay-local.mjs
```

The entire E2E suite uses **synthetic source receipts**, not real archived incident outcomes. No verified wildfire counts, predictive accuracy, probability, measured spread or extinguishment performance is claimed.
