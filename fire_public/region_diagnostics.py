"""Read-only, region-independent diagnostics for satellite candidate observations.

Satellite candidates are not confirmed wildfire incidents. This module performs no
upstream requests and makes no claims about wildfire probability or burned area.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from typing import Any, Iterable

EARTH_RADIUS_KM = 6371.0088


def _utc(value: str | datetime) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if dt.tzinfo is None:
        raise ValueError("Observation timestamps must be timezone-aware")
    return dt.astimezone(timezone.utc)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance, robust to the international date line."""
    a, b = radians(lat1), radians(lat2)
    dl = radians((lon2 - lon1 + 180) % 360 - 180)
    dlat = b - a
    h = sin(dlat / 2) ** 2 + cos(a) * cos(b) * sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(min(1.0, max(0.0, h))))


def summarize_circle(
    events: Iterable[dict[str, Any]],
    *,
    latitude: float,
    longitude: float,
    radius_km: float,
    as_of: str | datetime,
    window_hours: float = 24,
) -> dict[str, Any]:
    """Summarize candidate cell-hours within a worldwide circular search area.

    Counts refer to supplied observations, not independently confirmed fires.
    Events newer than `as_of` or outside the window are excluded.
    """
    from math import isfinite
    if not all(isfinite(float(x)) for x in (latitude, longitude, radius_km, window_hours)):
        raise ValueError("Region parameters must be finite")
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Latitude/longitude out of range")
    if not 0 < radius_km <= 20000 or not 0 < window_hours <= 168:
        raise ValueError("Invalid radius or observation window")

    at = _utc(as_of)
    selected: list[tuple[dict[str, Any], datetime]] = []
    for event in events:
        observed = _utc(event["observed_at"])
        age_hours = (at - observed).total_seconds() / 3600
        if not 0 <= age_hours <= window_hours:
            continue
        if distance_km(latitude, longitude, float(event["latitude"]),
                       float(event["longitude"])) <= radius_km:
            selected.append((event, observed))

    by_cell: dict[tuple[float, float], set[str]] = defaultdict(set)
    sensor_memberships: Counter[str] = Counter()
    for event, observed in selected:
        cell = (float(event["latitude"]), float(event["longitude"]))
        by_cell[cell].add(observed.strftime("%Y-%m-%dT%H"))
        sensor_memberships.update(set(event.get("sources") or []))

    latest = max((t for _, t in selected), default=None)
    return {
        "area": {"type": "circle", "latitude": latitude, "longitude": longitude,
                 "radius_km": radius_km},
        "as_of": at.isoformat(),
        "window_hours": window_hours,
        "candidate_cell_hours": len(selected),
        "distinct_observed_cells": len(by_cell),
        "cells_observed_in_multiple_hours": sum(len(hours) > 1 for hours in by_cell.values()),
        "last_observed_at": latest.isoformat() if latest else None,
        "sensor_memberships": dict(sorted(sensor_memberships.items())),
        "interpretation": "Unverified satellite thermal candidate observations; not wildfire counts.",
    }
