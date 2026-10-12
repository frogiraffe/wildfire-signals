"""Dependency-free, prospective-friendly evaluation of binary wildfire targets.

This module does not create fire labels from FIRMS pixels. Rows must contain
independently sourced binary outcomes and observation-time-safe predictions.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from math import log, isfinite
from typing import Any, Iterable


def _time(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timestamps require an explicit UTC offset")
    return dt.astimezone(timezone.utc)


def evaluate_binary(
    rows: Iterable[dict[str, Any]], *, bins: int = 10,
) -> dict[str, Any]:
    """Compare held-out predictions to a pre-specified constant baseline.

    Required fields: event_id, region_id, decision_at, label_available_at,
    label (0/1), prediction, baseline_prediction, split ('test').
    No training is performed. Each row is a held-out prediction whose label
    became known after its decision. Duplicate events in the same decision
    timestamp are rejected; callers must enforce train/test group separation.
    """
    if not isinstance(bins, int) or not 2 <= bins <= 50:
        raise ValueError("bins must be between 2 and 50")
    records = list(rows)
    if not records:
        raise ValueError("No independently labeled evaluation records")
    seen = set()
    counts: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    error = baseline_error = logloss = baseline_logloss = 0.0
    positives = 0
    eps = 1e-15
    for r in records:
        if r.get("split") != "test":
            raise ValueError("All evaluated records must be held-out test predictions")
        if not r.get("event_id") or not r.get("region_id"):
            raise ValueError("Event and region identifiers are required")
        decision = _time(r["decision_at"])
        label_time = _time(r["label_available_at"])
        if label_time <= decision:
            raise ValueError("Outcome availability must follow prediction decision time")
        key = (r["event_id"], decision)
        if key in seen:
            raise ValueError("Duplicate event at decision time")
        seen.add(key)
        label = r["label"]
        if type(label) is not int or label not in (0, 1):
            raise ValueError("Independent binary outcome label required")
        pred, base = float(r["prediction"]), float(r["baseline_prediction"])
        if not all(isfinite(p) and 0 <= p <= 1 for p in (pred, base)):
            raise ValueError("Probabilities must be finite and between 0 and 1")
        error += (pred - label) ** 2
        baseline_error += (base - label) ** 2
        p, b = max(eps, min(1 - eps, pred)), max(eps, min(1 - eps, base))
        logloss -= label * log(p) + (1 - label) * log(1 - p)
        baseline_logloss -= label * log(b) + (1 - label) * log(1 - b)
        positives += label
        bucket = min(bins - 1, int(pred * bins))
        counts[bucket][0] += 1
        counts[bucket][1] += label
    n = len(records)
    return {
        "n": n, "positives": positives, "prevalence": positives / n,
        "brier_score": error / n, "baseline_brier_score": baseline_error / n,
        "brier_skill_score": (1 - error / baseline_error) if baseline_error else None,
        "log_loss": logloss / n, "baseline_log_loss": baseline_logloss / n,
        "reliability_bins": [
            {"lower": i / bins, "upper": (i + 1) / bins,
             "count": counts[i][0], "observed_positive_rate":
                 counts[i][1] / counts[i][0]}
            for i in sorted(counts) if counts[i][0]
        ],
        "scope": "Held-out labeled records supplied by caller; no training or geographic generalization established",
    }
