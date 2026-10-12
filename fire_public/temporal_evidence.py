"""Read-only as-of timeline for satellite candidates across retained snapshots.

A candidate appearing in repeated snapshots is ONE observation, not repeated fire
activity. Snapshot collection gaps and failed sources remain explicit.
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any, Iterable

from .region_diagnostics import _utc, distance_km, summarize_circle


def regional_timeline(
    snapshots: Iterable[dict[str, Any]], *, latitude: float, longitude: float,
    radius_km: float, as_of: str, window_hours: float = 72,
    bucket_hours: int = 6,
) -> dict[str, Any]:
    """Construct timestamped observation buckets without using future receipts.

    Latest source health is reported separately. Historical snapshots contain
    overlapping windows, so candidates are de-duplicated by event_id, or by
    location/time/source tuple when an event ID is absent.
    """
    if not isinstance(bucket_hours, int) or bucket_hours < 1 or bucket_hours > 24:
        raise ValueError("bucket_hours must be an integer between 1 and 24")
    at = _utc(as_of)
    # Reuse argument validation from the worldwide circle contract.
    summarize_circle([], latitude=latitude, longitude=longitude,
                     radius_km=radius_km, as_of=at, window_hours=window_hours)
    eligible = []
    for snapshot in snapshots:
        captured = _utc(snapshot["manifest"]["last_scan_at"])
        if captured <= at:
            eligible.append((captured, snapshot))
    eligible.sort(key=lambda item: item[0])
    by_identity: dict[tuple[Any, ...], dict[str, Any]] = {}
    for captured, snapshot in eligible:
        for event in snapshot.get("events", []):
            observed = _utc(event["observed_at"])
            age = (at - observed).total_seconds() / 3600
            if not 0 <= age < window_hours or observed > captured:
                continue  # no future knowledge or observations outside target window
            if distance_km(latitude, longitude, float(event["latitude"]),
                           float(event["longitude"])) > radius_km:
                continue
            identity = (("id", str(event["event_id"])) if event.get("event_id")
                        else ("fallback", float(event["latitude"]),
                              float(event["longitude"]), observed.isoformat(),
                              tuple(sorted(event.get("sources") or []))))
            by_identity.setdefault(identity, event)

    n_buckets = int((window_hours + bucket_hours - 1) // bucket_hours)
    buckets = [0] * n_buckets
    for event in by_identity.values():
        age = (at - _utc(event["observed_at"])).total_seconds() / 3600
        idx = min(int(age // bucket_hours), n_buckets - 1)
        buckets[idx] += 1
    counts = [{"age_from_hours": i * bucket_hours,
               "age_to_hours": min((i + 1) * bucket_hours, window_hours),
               "candidate_observations": count}
              for i, count in enumerate(buckets)]
    latest = eligible[-1][1] if eligible else None
    errors = latest["manifest"].get("source_errors", []) if latest else None
    return {
        "area": {"latitude": latitude, "longitude": longitude, "radius_km": radius_km},
        "as_of": at.isoformat(), "window_hours": window_hours,
        "snapshot_count": len(eligible),
        "latest_scan_at": eligible[-1][0].isoformat() if eligible else None,
        "latest_data_status": latest["manifest"].get("data_status") if latest else None,
        "latest_source_errors": errors,
        "candidate_observations": len(by_identity),
        "buckets_newest_first": counts,
        "interpretation": "Observed satellite candidates, not verified fires or growth. "
                          "Unavailable coverage and delayed snapshots can reduce counts.",
    }
