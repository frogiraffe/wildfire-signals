"""Leakage-aware chronological and spatial holdouts for independently labeled cases.

This module splits supplied metadata; it does not produce independent wildfire
labels or prove feature availability. Caller must supply those separately.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable


def _utc(s: str) -> datetime:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Explicit timestamp timezone required")
    return dt.astimezone(timezone.utc)


def holdout_split(
    rows: Iterable[dict[str, Any]], *,
    test_start: str,
    embargo_hours: float = 0,
    heldout_regions: Iterable[str] = (),
) -> dict[str, Any]:
    """Create temporally embargoed train/test metadata sets.

    Region holdout mode: all cases in heldout regions with a decision >= test
    start are test; *all* earlier rows from heldout regions are excluded rather
    than leaked into train. Cases in other regions after test_start are excluded.

    Temporal mode (no heldout regions): earlier records may train; later test.
    A training outcome must be available strictly before the embargo boundary.
    An event identity cannot occur in both returned groups.
    """
    start = _utc(test_start)
    if not 0 <= embargo_hours <= 24 * 365:
        raise ValueError("Invalid embargo")
    threshold = start - timedelta(hours=embargo_hours)
    regions = set(heldout_regions)
    train: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    excluded = Counter()
    items = list(rows)
    identities = set()
    for r in items:
        if not r.get("event_id") or not r.get("region_id"):
            raise ValueError("event_id and region_id required")
        decision = _utc(r["decision_at"])
        label_available = _utc(r["label_available_at"])
        identity = (r["event_id"], decision)
        if identity in identities:
            raise ValueError("Duplicate event/decision pair")
        identities.add(identity)
        if label_available <= decision:
            raise ValueError("Label must be available after decision")
        if regions:
            if r["region_id"] in regions:
                if decision >= start:
                    test.append(r)
                else:
                    excluded["heldout_region_history"] += 1
            elif decision < threshold and label_available < threshold:
                train.append(r)
            else:
                excluded["other_region_nontraining"] += 1
        elif decision >= start:
            test.append(r)
        elif decision < threshold and label_available < threshold:
            train.append(r)
        else:
            excluded["embargo_or_unavailable_outcome"] += 1

    train_events = {r["event_id"] for r in train}
    test_events = {r["event_id"] for r in test}
    leaked = train_events & test_events
    if leaked:
        train = [r for r in train if r["event_id"] not in leaked]
        excluded["repeated_test_event_removed_from_training"] += sum(
            r["event_id"] in leaked for r in items if
            _utc(r["decision_at"]) < threshold)
    return {
        "train": train, "test": test,
        "excluded_by_reason": dict(sorted(excluded.items())),
        "test_start": start.isoformat(),
        "embargo_hours": embargo_hours,
        "heldout_regions": sorted(regions),
        "note": "Metadata-only splitting; geographic boundaries, labels and feature issue times must be audited separately.",
    }
