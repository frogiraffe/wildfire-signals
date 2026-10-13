# Analysis Engine v3 — preregistered historical observation cohort

This feature takes an explicit **global, non-overlapping sampling frame** and a regular series of historical **decision times**, then computes as-of FIRMS source statistics for every `(region_id, decision_at)` pair from the verified original pixel archive. It produces research-friendly CSV/JSONL, a manifest of source provenance and a self-contained HTML quality report. It is **not yet a wildfire training set**.

## Why this matters

The previous historical v2 tool analyzes one region and one time window. Model development requires a **repeated, explicitly defined unit of analysis** and reproducible feature availability at every decision time. Otherwise selecting only places with thermal candidates creates biased samples and falsely turns missing satellite detections into negative wildfire labels.

V3 starts with region/time sample pairs **whether or not a thermal candidate exists**. Each example contains the entire predefined 24/48/72/168/336-hour lookback, source audit and optional descriptive features. If any of the 12 bins lacks a complete receipt for any selected collection source, **every numeric modeling feature is null**; separately retained `observed_archive_subset` counts document the records that were seen without treating missing observations as zero. A region with zero candidate records may have `features.candidate_cell_hours=0` *only* when the collection-request audit is complete; its `target_label` still remains `null`. Completing collection requests **does not** verify VIIRS satellite overpasses, cloud-free conditions or the absence of wildfire.

No outcomes, negative-fire labels, forecasts, p-values, training partition or probability estimates are generated. **Every row has `model_training_allowed:false`**. The declared prediction target window is an empty placeholder for eventual **independently audited** future agency outcomes, not an agency/fire linkage by spatial proximity. Existing `evaluation_splits`, `historical_baseline` and `model_evaluation` are only used after valid target labels and feature availability are established.

## Offline usage

First build the existing original pixel SQLite (see [pixel archive](global-firms-pixel-archive.md)). Create a **private** JSON region list, such as [illustrative worldwide regions](../examples/observational-regions.json). Regions may be anywhere on Earth, but every selected circle must have a unique stable ID, radius 0.01–250 km and **must not overlap** any other selected circle (including across the antimeridian).

```sh
python -m fire_public.observational_cohort \
  --pixel-db /private/firms-pixels.sqlite3 \
  --regions-json examples/observational-regions.json \
  --start-at 2026-10-12T00:00:00Z \
  --end-at 2026-10-13T00:00:00Z \
  --cadence-hours 6 --lookback-hours 24 --target-hours 24 \
  --output-dir /private/firms-study-20261013
```

The decision interval is **start-inclusive/end-exclusive**, and every decision time must precede the latest archived scan capture. A project with only two daily research releases can generate study-frame rows, but **cannot claim a complete six-hourly observation record**; likely many rows will be censored. Sampling is capped at **256 region/decision pairs** across at most 12 non-overlapping circles. Cadences are 1/2/3/4/6/12/24 hours; target horizons are 6/12/24/48/72 hours. The selected horizon is a *predeclared future interval*, not a computed label.

Outputs, all local/private, new-only and explicitly verified by manifest SHA-256:

- `observations.jsonl`: complete observational records with source receipt digest, observed subset, source quality, null label and as-of feature timestamps
- `observations.csv`: flat, R/Python/Excel-friendly region/decision table; blank labels and censored features mean **unknown**, never class zero
- `manifest.json`: original archive capture support, locked geographic sampling frame, parameters and counts of censored/model-ineligible rows
- `quality.html`: responsive, local-only overview of sample coverage and source-data censoring, not a wildfire risk map

## Real original-FIRMS release integration test

[The research cohort CI workflow](../.github/workflows/test-observational-cohort.yml)
includes an isolated pull-request job that **pins the original published 12 and
13 October 2026 FIRMS evidence releases**. It verifies their release digests
and raw source-file checksums using the already existing importer, then runs
this study-frame engine against two widely separated illustrative regions.
It asserts zero fabricated outcome labels and publishes **aggregate-only**
research readiness reports as seven-day test artifacts; the verified raw
pixel files and SQLite database remain in the temporary CI environment.
The test has a strict 90 MiB compressed-download budget and fails if pinned
research source assets disappear rather than substituting synthetic data.

The [manual historical analysis workflow](../.github/workflows/run-historical-signal-analysis.yml)
also exports `observations.csv`, `observations.jsonl`, `manifest.json`
and `quality.html` for a single user-selected worldwide region alongside
the existing historical-statistical-analysis report. Its eight fixed
six-hourly decisions cover the 48 hours before the newest verified original
scan capture. This is a *readiness analysis*, not validation of wildfire
prediction accuracy.

## Scientific limitations and the next experiment

- An original collection receipt is **not** a geographic satellite detection opportunity. V3 flags any row with even a complete collector audit as `orbital_exposure_validated:false` and disallows model fitting without an external orbital/revisit and cloud/visibility audit.
- Only FIRMS thermal candidate observations, not independent wildfire incidents or weather at decision time, are present. Neither a missing candidate nor a source outage creates a negative case.
- Non-overlapping circles reduce spatial train/test contamination, but do not prove **spatial independence**; nearby storms, incidents, terrain and acquisition paths can share effects. Regions are sorted and their exact IDs and coordinates are held fixed.
- SHA-256 of archived receipt identities allows reproduction **relative to the original published files**, not independent government origin authentication or proof of physical wildfire.
- The next model experiment requires separately licensed/audited first-report fire positives **and independently justified negatives**, outcome publication times, source coverage, and genuinely observable historical predictors. Only then use embargoed time/geography splits and Brier/log-loss calibration against the existing reference models. Do not invent evaluation scores.

### Test

```sh
python -m unittest discover -s tests -p 'test_observational_cohort.py' -v
```

Tests use deterministic genuine `PixelArchive`-format synthetic source files and SQLite imports, including full and failed scanner periods, as-of late-arrival exclusion, zero candidate observations, antimeridian overlap, non-overlap holdouts and source-bounded JSONL/CSV/HTML export. They do not measure real model predictive performance.
