# Independently labeled outcome evaluation (offline research)

Wildfire Signals now has an executable research **baseline validation entrypoint** for cohorts prepared from genuinely independent outcome registries, with a private audited cohort manifest. It intentionally refuses to create positives from FIRMS heat pixels or negatives from the absence of a fire in agency active layers. **No valid public ground-truth cohort is bundled.** Running tests produces only synthetic-fixture metrics, not real wildfire prediction quality.

## Required inputs

Prepare a private UTF-8 `cohort.jsonl`, each line a JSON object:

```json
{"event_id":"unique-event-1","region_id":"independent-spatial-holdout-id","decision_at":"2025-08-01T00:00:00Z","feature_cutoff_at":"2025-08-01T00:00:00Z","label_available_at":"2025-08-03T00:00:00Z","label_verified_at":"2025-08-03T00:00:00Z","label":1,"label_source":"independent-outcome-registry","label_source_id":"verified-event-id","label_evidence_url":"https://example.org/independent-record","case_sampling_id":"audited-sampling-unit-1"}
```

A second required JSON `manifest.json` declares: `schema_version=1`, meaningful `target_name`, `target_definition`, `horizon_hours`, `unit_of_analysis`, `study_region`, `labeling_protocol`, `positive_label_rule`, `negative_label_rule`, `sampling_frame`, plus `negative_coverage_audited=true`, `independent_label_provenance_verified=true`, the HTTPS `ground_truth_source_url`, `rights_url`, `prepared_by` and timezone-aware `prepared_at`.

Both labels require source-specific independent verification. An agency incident appearing in a provider layer may be usable as a positive only when the target and provenance truly support it. A fire missing from a source feed is **never** an automatically valid negative. A negative requires a specific independently checked complete registry or reliable sampling protocol.

The script checks declared times, distinct event/decision pairs, source identifiers, manifest declarations and provenance URLs. It **cannot independently prove** that the claims in the manifest or the external source website are correct. Do not claim external validation without separate scientific review.

## Run

```bash
python -m fire_public.labeled_evaluation \
  --cohort /private/study/cohort.jsonl \
  --manifest /private/study/manifest.json \
  --test-start 2025-09-01T00:00:00Z \
  --embargo-hours 168 \
  --heldout-region withheld-region-id \
  --output /private/study/results.json
```

`--heldout-region` can be omitted for a strictly chronological test or repeated for multiple withheld regions. For the spatial test, all earlier data from held-out regions are explicitly excluded. Outcomes known after the train embargo boundary cannot train. Identical events may never leak between train/test. A Laplace-smoothed global pre-cutoff base rate is fitted on training labels, evaluated against the independently sourced test labels using Brier score, log-loss and reliability bins.

The output stores the exact input SHA-256 digests, cohort summary, split exclusion counts, target, metrics and source protocol reference, **without copying private individual cohort records**. The source files remain local, outside public Git. It prevents overwriting either input and will not replace existing outputs.

## Limitations

This is a reusable research evaluation workflow, not a pretrained predictive fire model. No real independent outcome data, defensible negative sampling frame or ground-truth license has been supplied or run here. Tests are synthetic, and numerical output from them cannot be presented as model performance. The script performs structural point-in-time checks but cannot audit all original raw weather/sensor model issue timestamps from a JSONL declaration. Some event-level censoring, reporting delay and data completeness must still be independently checked.

Required next scientific work: identify and license genuine independent outcome records for an explicit geography and prediction target, design a defensible negative sampling strategy, substantiate the coverage audit, then run this exact command against that **real** dataset with a reproducible source/version record.
