# Analysis Engine v4 — source-bound agency listing review for prospectively sampled FIRMS cohorts

This is a **private, offline, source-referenced research bridge**, not a model producing fire occurrence probabilities. It consumes exactly two inputs:

1. The unmodified `observations.jsonl` and `manifest.json` from [Analysis Engine v3](observational-study-cohort-v3.md) (predeclared region × decision UTC pairs, outcome horizon, feature lookback). Every target remains `null`, and the SHA-256 of the original cohort is checked before the bridge proceeds.
2. A private SQLite archive of original **prospective NIFC WFIGS and CWFIS** receipts, populated with `fire_public.receipt_history` or restored with `fire_public.agency_vault rebuild`. Source status `complete`/`failed`/`deferred`, per-source incident presence, original capture time, source ID, run and receipt digests are kept.

The link is deliberately *weak*: a source listing **at a georeferenced point within the sampled circle** during the future horizon is an investigation lead. The agency point is not necessarily a fire perimeter or exact ignition point. A near-same-time FIRMS cell is not proven to refer to that agency identity; **the script never joins a pixel to a fire event ID**.

## Local usage (only if original agency receipts actually exist)

```sh
# Build local agency history from genuine, still-accessible original captures.
python -m fire_public.agency_vault rebuild \
  --vault /private/wildfire-original-vault \
  --db /private/agency-prospective.sqlite3

# Generate private leads and per-region/time source evidence audit.
python -m fire_public.agency_cohort_review \
  --cohort-dir /private/firms-study-20261013 \
  --agency-db /private/agency-prospective.sqlite3 \
  --output-dir /private/agency-review-20261013

# To answer only what was archived by a specified date, add:
# --through 2026-10-13T00:00:00Z
```

All outputs are private, new-only, mode 0700 directory / 0600 files, and outside Git:

- `agency-review-leads.jsonl`: source-specific `(provider, official_id)` leads with original agency point, source rights URL, captured time, scan/run SHA-256, observed agency status and `first_post_decision_listed_at`. The row explicitly says `independent_outcome_label:null`, `negative_fire_label:null`, `ignition_time_established:false` and `review_status:unresolved`.
- `agency-source-coverage.jsonl`: one record per original sampled region/decision, **including all cases with no agency lead**, with agency source completions, failures, deferrals, last predecision receipt, right-censoring and explicit `target_label:null`. A source missing a fire is not a reliable negative.
- `manifest.json`: proof hashes of every output, count of sampled decisions and source listings, zero independently confirmed labels, exact source-cohort manifest SHA-256 and interpretation limitations.
- `review.html`: local-only, script-free aggregate summary with source status and uncertainty.

**Timeline rules:** predecision agency receipts and future receipts are strictly distinguished. Only receipts captured at or after the decision time can be considered future review evidence; new agency IDs first seen after that time are marked `first_in_available_receipt_history_not_proven_ignition`, while provider-specific IDs known before that time are marked `preexisting_agency_source_listing`. An identity previously seen outside the circle remains *preexisting* if it later enters the circle. Failed or deferred sources cannot create new listings; absences in successful scans cannot create extinction, negative fire or ignition labels.

If the user-specified `--through` cutoff or latest retained agency receipt occurs before an outcome horizon finishes, the outcome audit is **right-censored**. Even if a full day of source listings is captured, the registry may have incomplete geography, late publication and other sampling limitations. All `horizon_fully_audited` flags remain false; observed source listings are not converted to training truth.

**Methodological limits:** This output is a bounded list of potential human review tasks, not a public or globally validated wildfire outcome cohort. NIFC WFIGS and CWFIS are jurisdiction-specific and may both refer to the same physical fire, but cross-provider event identity is *not* inferred. Fire/non-fire labeling requires independently audited event identity, target time, negative registry coverage, source timeliness and reviewer decisions with the existing [independent label review](independent-label-review-workbench.md) gates. Source provenance timestamps are original **archive capture** times, not guaranteed initial upstream government publication times.

## Test

```sh
python -m unittest discover -s tests -p 'test_agency_cohort_review.py' -v
```

Deterministic test fixtures pass genuine-formatted prospective NIFC/CWFIS receipts through the existing source import and original NASA FIRMS research-format pixel imports, then run the v3 sampling and this source association bridge. They test antimeridian, source failures, previously known provider IDs, future labels not leaked into features, incomplete horizons, missing agency listings **not** becoming no-fire cases, source-manifest tampering, CLI output and private file permissions.

**Real-data status:** The existing real FIRMS release test imported **319,129 unique thermal detections** from the 12–13 October original archives. That does **not** imply matching historical *prospective* NIFC/CWFIS source receipts have been collected or independently fire-labeled. This PR does not invent, publish or automatically scrape such missing agency records.
