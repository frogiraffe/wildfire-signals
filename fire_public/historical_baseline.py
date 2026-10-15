"""Reproducible empirical base-rate experiment for independently labeled cases.

No FIRMS-based pseudo-labels. The caller provides independently labeled cases
and auditable availability times. This is a baseline, not a wildfire forecast.
"""
from __future__ import annotations

from math import isfinite
from typing import Any, Iterable

from .evaluation_splits import holdout_split
from .feature_availability_audit import audit_asof_features
from .model_evaluation import evaluate_binary


def _check_case(row: dict[str, Any]) -> None:
    if type(row.get("label")) is not int or row["label"] not in (0, 1):
        raise ValueError("Independent binary labels (0/1) required")
    if not row.get("label_source") or not row.get("label_source_id"):
        raise ValueError("Auditable independent outcome provenance required")


def historical_rate_experiment(
    records: Iterable[dict[str, Any]], *, test_start: str,
    embargo_hours: float = 0, heldout_regions: Iterable[str] = (),
    smoothing: float = 1.0,
) -> dict[str, Any]:
    """Fit global pre-cutoff Laplace-smoothed prevalence and evaluate on holdout.

    The constant probability is learned *only* from training labels known before
    the cutoff. This intentionally simple reference avoids geographic memorization.
    Source evidence, feature-time integrity and completeness remain caller duties.
    """
    items = list(records)
    if not isfinite(smoothing) or smoothing < 0 or smoothing > 1000:
        raise ValueError("smoothing must be between 0 and 1000")
    for r in items:
        _check_case(r)
    provided = [r for r in items if "features" in r]
    if provided:
        if len(provided) != len(items):
            raise ValueError("Partial feature evidence: every case must provide features")
        audit = audit_asof_features([
            {"case_id": f"case-{i}", "decision_at": row["decision_at"],
             "features": row["features"]}
            for i, row in enumerate(items)
        ])
        if audit["ineligible"]:
            raise ValueError("Feature as-of chronology/provenance audit failed")
    else:
        audit = None
    split = holdout_split(items, test_start=test_start, embargo_hours=embargo_hours,
                          heldout_regions=heldout_regions)
    train, test = split["train"], split["test"]
    if not train or not test:
        raise ValueError("Nonempty independent training and test cohorts required")
    positive = sum(r["label"] for r in train)
    total = len(train)
    rate = (positive + smoothing) / (total + 2 * smoothing)
    if not 0 <= rate <= 1:
        raise ValueError("Invalid fitted base rate")
    heldout_predictions = [
        {**r, "split": "test", "prediction": rate, "baseline_prediction": rate}
        for r in test
    ]
    evaluation = evaluate_binary(heldout_predictions)
    return {
        "method": "laplace_smoothed_historical_base_rate",
        "feature_availability_audit": audit,
        "train_n": total, "train_positive": positive, "test_n": len(test),
        "fit_rate": rate, "smoothing": smoothing,
        "split": {k: v for k, v in split.items() if k not in ("train", "test")},
        "evaluation": evaluation,
        "scientific_status": "experimental_baseline_only",
        "warning": "Requires independently verified labels, as-of features, and documented geographic coverage; no global fire probability claim.",
    }
