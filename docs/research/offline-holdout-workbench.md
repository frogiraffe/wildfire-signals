# Offline holdout research workbench

This is a **local private experimental** scientific eligibility workflow, not a
fire detection model or a public forecast. It extends draft #68, which itself
depends on draft #67 and the earlier stacked research PRs.

## Inputs

- Researcher-provided independently labeled JSONL complying with
  `fire_public.labeled_evaluation._audit_rows`, plus the mandatory manifest
  accepted by `_manifest`. The independent label source and negative-observation
  coverage must be audited outside this program.
- Each JSONL record additionally supplies:
  - `split`: explicitly pre-assigned `train` or `test`
  - `feature_latest_available_at`: explicit UTC time at which the last used
    predictive feature became available. Must not exceed `decision_at`.
- The upstream independent cohort contract provides `event_id`,
  `region_id`, `case_sampling_id`, `decision_at`,
  `label_available_at`, and binary `label`.

This strict holdout requires disjoint regions and event IDs, train observations
strictly before test observations (including user-supplied embargo), and
both classes in both partitions. These are intentionally conservative gates,
not an automatic model-selection algorithm.

## Usage

```bash
python -m fire_public.holdout_workbench \
  --cohort /private/research/cohort.jsonl \
  --manifest /private/research/manifest.json \
  --embargo-hours 168 \
  --output /private/research/holdout-report.json \
  --html /private/research/holdout-report.html
python -m unittest tests.test_holdout_audit tests.test_holdout_workbench -v
```

Output paths must be new; cohort or manifest cannot be overwritten.
No external services, live collector changes, new scheduled job, or paid API.
Reports contain SHA-256 source checksums, aggregate class and sample counts,
failed gates and limitations; they intentionally omit case-level identifiers,
coordinates, URLs to private evidence and features.

## Scientific interpretation

`eligible_for_model_evaluation = true` means only that the provided data
passes the defined holdout-integrity checks. It **does not establish** that
source documents are authentic, reviews are independent, labels are correct,
fire-negative windows have verified observation coverage, or a model
generalizes. The tool outputs no measured model skill. Inputs in tests are
synthetic and are not empirical wildfire data.

This workflow does not replace regional case-control study design, event-wise
grouped cross-validation, coverage audits, threshold pre-registration,
discrimination/calibration measurements, or out-of-region external validation.

## Safeguards and open review

The workbench rejects missing/oversized/symlinked source files, oversized
JSONL lines, invalid label contracts and split leakage. HTML escapes untrusted
title and gate text and uses a no-network Content Security Policy.

Before integration, run the full Python suite, public JS suite, and any
applicable CI, then audit that no source or identifier enters public reports.
`main` and live Cloudflare Pages remain untouched by this draft PR.
