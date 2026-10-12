"""Offline multi-source context for historical agency evidence reports.

Enriches already-archived agency records with independently stored FIRMS
candidate observations and NWS forecast receipts. Does not fetch live data,
link individual satellite cells to agency incidents, or produce fire labels.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from .history import _timestamp
from .region_diagnostics import distance_km
from .decision_evidence import (_forecast_covers_decision, MAX_WEATHER_DISTANCE_KM)
from .weather_pilot import FIELDS, _valid_interval

MAX_SATELLITE_ROWS = 50000
MAX_WEATHER_ROWS = 2000
WINDOW_CHOICES = (6, 24, 72)


def _readonly(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"weather archive does not exist: {path}")
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    return db


def _point(payload: dict) -> tuple[float, float] | None:
    data = payload.get("point", payload)
    if not isinstance(data, dict):
        return None
    a, b = data.get("latitude"), data.get("longitude")
    if (isinstance(a, bool) or isinstance(b, bool)
            or not isinstance(a, (int, float)) or not isinstance(b, (int, float))
            or not math.isfinite(a) or not math.isfinite(b)
            or not -90 <= a <= 90 or not -180 <= b <= 180):
        return None
    return float(a), float(b)


def archived_candidates(db: sqlite3.Connection, *, at: str,
                        hours: int = 72, region: dict | None = None) -> dict:
    """Separate candidate cell-hour coverage, never wildfire incident counts."""
    if type(hours) is not int or hours not in WINDOW_CHOICES:
        raise ValueError("Candidate window must be 6, 24 or 72 hours")
    cutoff = _timestamp(at)
    start = (datetime.fromisoformat(cutoff) - timedelta(hours=hours)).isoformat()
    rows = db.execute("""
        SELECT id, source_id, observed_at, captured_at, payload_json
        FROM observations
        WHERE subject_kind='satellite_candidate'
          AND observed_at >= ? AND observed_at <= ? AND captured_at <= ?
        ORDER BY captured_at DESC, observed_at DESC, id DESC LIMIT ?
    """, (start, cutoff, cutoff, MAX_SATELLITE_ROWS + 1)).fetchall()
    truncated = len(rows) > MAX_SATELLITE_ROWS
    rows = rows[:MAX_SATELLITE_ROWS]

    unique = set()
    cells = defaultdict(set)
    sensor_counts = Counter()
    timestamps = []
    missing_location = 0
    outside = 0
    for row in rows:
        payload = json.loads(row["payload_json"])
        point = _point(payload)
        if point is None:
            missing_location += 1
            if region is not None:
                continue
        elif (region is not None and distance_km(region["latitude"],
                 region["longitude"], *point) > region["radius_km"]):
            outside += 1
            continue
        # Later re-captures / source corrections are not additional cell-hours.
        identity = (row["source_id"], row["observed_at"])
        if identity in unique:
            continue
        unique.add(identity)
        when = datetime.fromisoformat(row["observed_at"])
        hour = when.replace(minute=0, second=0, microsecond=0).isoformat()
        if point is not None:
            cells[(round(point[0], 4), round(point[1], 4))].add(hour)
        for sensor in set(payload.get("sources") or []):
            if isinstance(sensor, str):
                sensor_counts[sensor] += 1
        timestamps.append(row["observed_at"])
    return {
        "evidence_kind": "satellite_thermal_candidate",
        "window_hours": hours,
        "available_archive_records": len(unique),
        "distinct_observed_cells": len(cells),
        "cells_observed_in_multiple_hours": sum(len(seen) > 1 for seen in cells.values()),
        "latest_observed_at": max(timestamps) if timestamps else None,
        "source_memberships": dict(sorted(sensor_counts.items())),
        "missing_location_records": missing_location,
        "outside_selected_region": outside,
        "row_limit_reached": truncated,
        "no_fire_inference": True,
        "note": "Archived unconfirmed satellite thermal candidates only. Missing collection does not prove fire absence.",
    }


def _forecast_values(payload: dict, instant: datetime) -> dict:
    values = {}
    for name, (expected_unit, valid_value) in FIELDS.items():
        field = payload.get("fields", {}).get(name)
        if not isinstance(field, dict) or field.get("uom") != expected_unit:
            continue
        for row in field.get("values", []):
            try:
                start, end = _valid_interval(row.get("validTime"))
            except (TypeError, ValueError):
                continue
            value = row.get("value")
            if (start <= instant < end and isinstance(value, (int, float))
                    and not isinstance(value, bool) and math.isfinite(value)
                    and valid_value(value)):
                values[name] = {"value": value, "unit": expected_unit,
                                "valid_time": row["validTime"]}
                break
    return values


def archived_weather_context(weather_db: str | Path, incidents: list[dict],
                             *, at: str) -> dict:
    """Resolve nearest as-of NWS forecast for each agency event, if present.

    The 5km gate is only contextual proximity to an NWS query point; it is
    not proof of a fire/weather observation at that location.
    """
    cutoff = _timestamp(at)
    instant = datetime.fromisoformat(cutoff)
    with closing(_readonly(weather_db)) as db:
        rows = db.execute("""
            SELECT id,source_id,observed_at,captured_at,source_url,rights_url,payload_json
            FROM observations
            WHERE subject_kind='weather_forecast_snapshot' AND provider='nws_grid'
              AND observed_at <= ? AND captured_at <= ?
            ORDER BY captured_at DESC, observed_at DESC, id DESC LIMIT ?
        """, (cutoff, cutoff, MAX_WEATHER_ROWS + 1)).fetchall()
    truncated = len(rows) > MAX_WEATHER_ROWS
    forecasts = []
    for row in rows[:MAX_WEATHER_ROWS]:
        payload = json.loads(row["payload_json"])
        point = _point(payload)
        if point:
            forecasts.append((row, payload, point))
    results = []
    for incident in incidents:
        point = incident.get("location")
        event_point = _point(point) if point else None
        found = None
        if event_point:
            for row, payload, forecast_point in forecasts:
                distance = distance_km(*event_point, *forecast_point)
                if distance > MAX_WEATHER_DISTANCE_KM:
                    continue
                if not _forecast_covers_decision(payload, instant):
                    continue
                found = (row, payload, distance)
                break  # freshest eligible capture wins
        context = {
            "status": ("available_forecast" if found else
                       "event_location_missing" if not event_point else
                       "no_as_of_valid_nearby_forecast"),
            "model_ready": False,
            "context_distance_limit_km": MAX_WEATHER_DISTANCE_KM,
            "source_id": None, "captured_at": None, "issued_at": None,
            "distance_km": None, "source_url": None, "rights_url": None,
            "evidence_id": None, "values": {},
        }
        if found:
            row, payload, distance = found
            context.update(source_id=row["source_id"],captured_at=row["captured_at"],
                           issued_at=row["observed_at"],distance_km=round(distance,3),
                           evidence_id=row["id"],source_url=row["source_url"],
                           rights_url=row["rights_url"],
                           values=_forecast_values(payload,instant))
        results.append({"event_id": incident["event_id"], "forecast": context})
    return {
        "provider": "nws_grid",
        "scope": "US NWS captured forecast receipts only; no global weather availability claim",
        "decision_at": cutoff,
        "eligible_archive_forecasts": len(forecasts),
        "archive_row_limit_reached": truncated,
        "event_contexts": results,
    }
