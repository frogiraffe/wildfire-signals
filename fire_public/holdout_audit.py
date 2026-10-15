"""Fail-closed temporal/geographic holdout audit for independently labeled fire cohorts.

This module does not create labels, train a model, or estimate predictive skill.
It accepts an explicitly declared split and checks leakage before any evaluation.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
import math

MAX_ROWS = 100_000


def _time(value):
    if not isinstance(value, str):
        raise ValueError("UTC timestamp required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamps must be explicitly UTC")
    return parsed.astimezone(timezone.utc)


def _identifier(value, name):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 200:
        raise ValueError(f"{name} must be a nonempty identifier")
    return value.strip()


def audit_holdout(rows, *, embargo_hours=0, require_both_classes=True):
    """Audit a fixed train/test partition; never manufacture a partition or labels.

    Required per row: sampling_unit_id, event_id, region_id, feature_as_of,
    label_available_at, label (integer 0/1), and split ('train'/'test').
    Event and region holdouts are enforced across partitions, intentionally strict.
    Return only eligibility metadata; do not report a performance metric.
    """
    if type(embargo_hours) not in (int, float) or not math.isfinite(embargo_hours) or not 0 <= embargo_hours <= 8760:
        raise ValueError("embargo_hours must be finite, from 0 to 8760")
    if type(require_both_classes) is not bool:
        raise ValueError("require_both_classes must be boolean")
    if not isinstance(rows, list) or not 2 <= len(rows) <= MAX_ROWS:
        raise ValueError("bounded list with at least two labeled rows required")

    units = set()
    partitions = {"train": [], "test": []}
    events = {"train": set(), "test": set()}
    regions = {"train": set(), "test": set()}
    counts = {"train": Counter(), "test": Counter()}
    failures = set()

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each row must be an object")
        unit = _identifier(row.get("sampling_unit_id"), "sampling_unit_id")
        event = _identifier(row.get("event_id"), "event_id")
        region = _identifier(row.get("region_id"), "region_id")
        if unit in units:
            failures.add("duplicate_sampling_unit")
        units.add(unit)
        split = row.get("split")
        if split not in partitions:
            raise ValueError("split must be train or test")
        label = row.get("label")
        if type(label) is not int or label not in (0, 1):
            failures.add("unknown_or_invalid_label")
        else:
            counts[split][label] += 1
        feature_time = _time(row.get("feature_as_of"))
        label_time = _time(row.get("label_available_at"))
        if label_time < feature_time:
            failures.add("label_before_feature_cutoff")
        # Evaluate as-of predictability separately from retrospective labels.
        if "feature_latest_available_at" not in row:
            failures.add("missing_feature_availability")
        else:
            available_time = _time(row["feature_latest_available_at"])
            if available_time > feature_time:
                failures.add("future_feature_leakage")
        partitions[split].append(feature_time)
        events[split].add(event)
        regions[split].add(region)

    if not partitions["train"] or not partitions["test"]:
        failures.add("empty_partition")
    if events["train"] & events["test"]:
        failures.add("event_overlap")
    if regions["train"] & regions["test"]:
        failures.add("region_overlap")
    if partitions["train"] and partitions["test"]:
        boundary = max(partitions["train"]) + timedelta(hours=embargo_hours)
        if boundary >= min(partitions["test"]):
            failures.add("temporal_or_embargo_overlap")
    if require_both_classes:
        for split in ("train", "test"):
            if counts[split][0] == 0 or counts[split][1] == 0:
                failures.add("missing_class_" + split)

    return {
        "schema_version": 1,
        "eligible_for_holdout_evaluation": not failures,
        "failed_gates": sorted(failures),
        "train_rows": len(partitions["train"]),
        "test_rows": len(partitions["test"]),
        "train_class_counts": {"negative": counts["train"][0], "positive": counts["train"][1]},
        "test_class_counts": {"negative": counts["test"][0], "positive": counts["test"][1]},
        "embargo_hours": embargo_hours,
        "measured_skill": None,
        "interpretation": "Split-leakage eligibility only; labels and independent negative coverage must be validated upstream.",
    }
