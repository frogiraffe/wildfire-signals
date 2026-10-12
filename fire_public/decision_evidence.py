"""Read-only decision-time evidence audit, never a prediction or training label."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .history import _fire_event_id, _timestamp
from .weather_pilot import FIELDS, _valid_interval

MAX_WEATHER_DISTANCE_KM = 5.0  # Pilot proximity gate, not fire or grid equivalence.
REQUIRED_WEATHER_FIELDS = ("windSpeed", "temperature", "relativeHumidity")


def _open_readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _point(payload: dict) -> tuple[float, float] | None:
    if not isinstance(payload, dict):
        return None
    location = payload.get("point", payload)
    if not isinstance(location, dict):
        return None
    latitude, longitude = location.get("latitude"), location.get("longitude")
    if (isinstance(latitude, bool) or isinstance(longitude, bool) or
            not isinstance(latitude, (int, float)) or
            not isinstance(longitude, (int, float)) or
            not math.isfinite(latitude) or not math.isfinite(longitude) or
            not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        return None
    return float(latitude), float(longitude)


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    difference_latitude, difference_longitude = lat2 - lat1, lon2 - lon1
    haversine = (math.sin(difference_latitude / 2) ** 2 +
                 math.cos(lat1) * math.cos(lat2) * math.sin(difference_longitude / 2) ** 2)
    return 6371.0088 * 2 * math.asin(min(1.0, math.sqrt(haversine)))


def _forecast_covers_decision(payload: dict, instant: datetime) -> bool:
    try:
        start, end = _valid_interval(payload["source_valid_times"])
    except (KeyError, TypeError, ValueError):
        return False
    if not start <= instant < end:
        return False
    fields = payload.get("fields")
    if not isinstance(fields, dict):
        return False
    for name in REQUIRED_WEATHER_FIELDS:
        field = fields.get(name)
        expected_unit, valid_value = FIELDS[name]
        if (not isinstance(field, dict) or field.get("uom") != expected_unit
                or not isinstance(field.get("values"), list)):
            return False
        available = False
        for entry in field["values"]:
            if not isinstance(entry, dict):
                continue
            try:
                beginning, ending = _valid_interval(entry.get("validTime"))
            except ValueError:
                continue
            value = entry.get("value")
            if (beginning <= instant < ending and isinstance(value, (int, float))
                    and not isinstance(value, bool) and math.isfinite(value)
                    and valid_value(value)):
                available = True
                break
        if not available:
            return False
    return True


def audit_decision(event_db: Path, weather_db: Path, *, provider: str,
                   source_id: str, decision_at: str, weather_source_id: str) -> dict:
    """Audit an explicitly nominated agency event and NWS grid context.

    Receipt timestamps are local assertions; this gate does not validate their
    clock provenance, outcome labels, forecast skill, or source coverage.
    """
    cutoff = _timestamp(decision_at)
    if provider not in {"nifc_wfigs", "cwfis"} or not source_id or not weather_source_id:
        raise ValueError("explicit agency and weather source identities required")
    with closing(_open_readonly(Path(event_db))) as events, \
            closing(_open_readonly(Path(weather_db))) as weather:
        agency_rows = events.execute("""
            SELECT id, record_type, observed_at, captured_at, payload_json
            FROM observations
            WHERE subject_kind = 'agency_incident' AND provider = ? AND source_id = ?
              AND observed_at <= ? AND captured_at <= ?
            ORDER BY captured_at, observed_at, id
        """, (provider, source_id, cutoff, cutoff)).fetchall()
        has_event_links = events.execute("""
            SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'fire_event_sources'
        """).fetchone() is not None
        event_row = events.execute("""
            SELECT event_id FROM fire_event_sources
            WHERE provider = ? AND source_id = ? AND first_captured_at <= ?
        """, (provider, source_id, cutoff)).fetchone() if has_event_links else None
        report = {"schema_version": 1, "decision_at": cutoff,
                  "agency_source": f"{provider}:{source_id}",
                  "fire_event_id": (event_row["event_id"] if event_row else
                                    _fire_event_id(provider, source_id) if agency_rows and
                                    not has_event_links else None),
                  "agency_observation_ids": [row["id"] for row in agency_rows],
                  "agency_latest_captured_at": agency_rows[-1]["captured_at"] if agency_rows else None,
                  "weather_source": f"nws_grid:{weather_source_id}",
                  "weather_observation_id": None, "weather_captured_at": None,
                  "distance_km": None, "max_weather_distance_km": MAX_WEATHER_DISTANCE_KM,
                  "exclusions": [], "joint_input_available": False,
                  "model_ready": False}
        if not agency_rows:
            report["exclusions"].append("agency_not_yet_received")
            return report
        agency_point = None
        for row in reversed(agency_rows):
            if row["record_type"] == "incident_status":
                agency_point = _point(json.loads(row["payload_json"]))
                if agency_point is not None:
                    break
        if agency_point is None:
            report["exclusions"].append("agency_location_unknown")
            return report
        weather_rows = weather.execute("""
            SELECT id, observed_at, captured_at, payload_json
            FROM observations
            WHERE subject_kind = 'weather_forecast_snapshot' AND provider = 'nws_grid'
              AND source_id = ? AND observed_at <= ? AND captured_at <= ?
            ORDER BY captured_at DESC, observed_at DESC, id DESC
        """, (weather_source_id, cutoff, cutoff)).fetchall()
        if not weather_rows:
            report["exclusions"].append("weather_not_yet_received")
            return report
        found_point = False
        valid_location_without_values = False
        for row in weather_rows:
            payload = json.loads(row["payload_json"])
            weather_point = _point(payload)
            if weather_point is None:
                continue
            found_point = True
            distance = _distance_km(agency_point, weather_point)
            report["distance_km"] = round(distance, 3)
            if distance <= MAX_WEATHER_DISTANCE_KM:
                if not _forecast_covers_decision(payload, datetime.fromisoformat(cutoff)):
                    valid_location_without_values = True
                    continue
                report["weather_observation_id"] = row["id"]
                report["weather_captured_at"] = row["captured_at"]
                report["joint_input_available"] = True
                return report
        report["exclusions"].append("weather_validity_missing" if valid_location_without_values
                                    else "weather_point_too_far" if found_point
                                    else "weather_location_unknown")
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only decision-time evidence audit")
    parser.add_argument("--events-db", type=Path, required=True)
    parser.add_argument("--weather-db", type=Path, required=True)
    parser.add_argument("--provider", choices=("nifc_wfigs", "cwfis"), required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--decision-at", required=True)
    parser.add_argument("--weather-source-id", required=True)
    arguments = parser.parse_args()
    result = audit_decision(arguments.events_db, arguments.weather_db,
        provider=arguments.provider, source_id=arguments.source_id,
        decision_at=arguments.decision_at, weather_source_id=arguments.weather_source_id)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
