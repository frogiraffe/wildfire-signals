# As-of feature availability audit (experimental)

The standalone `fire_public.feature_availability_audit.audit_asof_features` utility checks whether recorded predictors were both observed and verifiably available by a historical decision timestamp. It does **not** authorize modeling, infer non-fire labels, or verify whether a satellite actually observed a region.

Input is an iterable of records with a unique `case_id`, timezone-aware `decision_at`, and nonempty `features` dictionary. Each named feature supplies `value`, `observed_at`, `available_at`, and a nonempty `source_id`. Unknown values, missing evidence, naive timestamps, observations after decision time and future availability all mark a case ineligible. Duplicate identifiers or invalid top-level input raise `ValueError`. Results include per-case violation codes and aggregate counts.

```python
from fire_public.feature_availability_audit import audit_asof_features

result = audit_asof_features([{
    "case_id": "region1-2026-10-01T12",
    "decision_at": "2026-10-01T12:00:00Z",
    "features": {"temperature": {
        "value": 28.0, "observed_at": "2026-10-01T10:00:00Z",
        "available_at": "2026-10-01T11:00:00Z",
        "source_id": "station-version-1",
    }},
}])
assert result["eligible"] == 1
assert result["model_training_authorized"] is False
```

Run `python -m unittest tests.test_feature_availability_audit -v` from repository root, then the full Python suite. This gate is deliberately orthogonal to the independent-label review, source coverage, orbital exposure, geographic/time holdout and outcome-adjudication requirements. A structural pass **cannot** be interpreted as evidence that wildfire model evaluation is scientifically valid.

Engineering integration: use this check before passing labeled datasets to experimental baselines; explicitly require the remaining source/label/split checks separately. It makes no network requests and does not modify public collection or deployment.

## Labeled evaluator integration

When `run_evaluation` receives a JSONL cohort with `features` on **every** row, it propagates the same per-case chronology audit into `feature_availability_audit` in the private aggregate report, and rejects any ineligible feature. If no rows carry feature-level evidence, the field is `null` (not a passed check). Mixing rows with and without feature evidence is refused. These checks are structural; a source identifier does not prove provider authenticity.

The output remains a research baseline, not a forecast. Historical exposure, independently verified positives and negatives, availability chronology, geographic holdout and source licensing still require separate audits.

Optional `issued_at` can record a provider's source issue/publication timestamp; if supplied, it must be timezone-aware and not later than the decision. Non-finite floating point values and booleans are rejected as evidence values. These are structural checks, not independent proof of issue-time provenance.
