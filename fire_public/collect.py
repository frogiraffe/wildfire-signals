"""Bounded global NASA FIRMS candidates and separate NIFC agency incidents."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FIRMS_SOURCES = ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/world/1"
NIFC_URL = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
            "WFIGS_Incident_Locations_Current/FeatureServer/0/query")
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
MAX_CSV_ROWS = 250_000
MAX_NIFC_PAGES = 10
PAGE_SIZE = 1000


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(timezone.utc)


def parse_firms_csv(raw: str, source: str, *, at: datetime) -> list[dict]:
    """Group pixels by 0.05-degree cell and hour; no fire confirmation implied."""
    at = _utc(at)
    if source not in FIRMS_SOURCES:
        raise ValueError("unsupported FIRMS source")
    reader = csv.DictReader(io.StringIO(raw))
    required = {"latitude", "longitude", "acq_date", "acq_time"}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("FIRMS CSV schema unavailable")
    groups: dict[tuple[int, int, str], dict] = {}
    for index, row in enumerate(reader):
        if index >= MAX_CSV_ROWS:
            raise ValueError("FIRMS row budget exceeded")
        try:
            lat, lon = float(row["latitude"]), float(row["longitude"])
            observed = datetime.strptime(row["acq_date"] + str(row["acq_time"]).zfill(4),
                                         "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError, KeyError):
            continue
        if (not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90
                or not -180 <= lon <= 180 or observed > at
                or observed < at - timedelta(hours=24)):
            continue
        cell = (math.floor(lat * 20), math.floor(lon * 20),
                observed.strftime("%Y-%m-%dT%H:00:00+00:00"))
        item = groups.get(cell)
        if item is None:
            event_id = "firms-" + hashlib.sha256(repr(cell).encode()).hexdigest()[:20]
            item = groups[cell] = {"kind": "satellite_candidate", "event_id": event_id,
                "latitude": round((cell[0] + .5) / 20, 4),
                "longitude": round((cell[1] + .5) / 20, 4),
                "first_at": observed.isoformat(), "observed_at": observed.isoformat(),
                "received_at": at.isoformat(), "sources": [source],
                "detection_count": 0, "radius_km": 8, "source_agreement": False,
                "aggregation": "0.05 degree cell by UTC hour"}
        item["detection_count"] += 1
        item["observed_at"] = max(item["observed_at"], observed.isoformat())
        item["first_at"] = min(item["first_at"], observed.isoformat())
    return list(groups.values())


def parse_nifc_page(raw: dict, *, at: datetime) -> list[dict]:
    if raw.get("error") or not isinstance(raw.get("features"), list):
        raise ValueError("NIFC response schema unavailable")
    incidents = []
    for feature in raw["features"]:
        attrs, geo = feature.get("attributes") or {}, feature.get("geometry") or {}
        if attrs.get("IncidentTypeCategory") != "WF" or not attrs.get("IrwinID"):
            continue
        try:
            lat, lon = float(geo["y"]), float(geo["x"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        modified = attrs.get("ModifiedOnDateTime_dt")
        modified_at = (datetime.fromtimestamp(modified / 1000, timezone.utc).isoformat()
                       if isinstance(modified, (int, float)) and math.isfinite(modified) else None)
        incidents.append({"kind": "agency_incident", "provider": "nifc_wfigs",
            "official_id": str(attrs["IrwinID"]),
            "name": str(attrs.get("IncidentName") or "")[:100], "incident_kind": "WF",
            "latitude": lat, "longitude": lon, "modified_at": modified_at,
            "last_seen_at": _utc(at).isoformat()})
    return incidents


def _get(url: str) -> bytes:
    with urlopen(Request(url, headers={"User-Agent":"FireMonitorPublic/0.1 (+https://github.com/frogiraffe)"}),
                 timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"upstream HTTP {response.status}")
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("upstream response byte budget exceeded")
    return data


def fetch_firms(key: str, source: str, *, at: datetime) -> list[dict]:
    if not key or any(char in key for char in "/?#"):
        raise ValueError("invalid FIRMS map key")
    raw = _get(FIRMS_URL.format(key=key, source=source)).decode("utf-8-sig")
    return parse_firms_csv(raw, source, at=at)


def fetch_nifc(*, at: datetime) -> list[dict]:
    records = {}
    for page in range(MAX_NIFC_PAGES):
        query = urlencode({"f":"json", "where":"IncidentTypeCategory='WF'",
            "outFields":"IrwinID,IncidentName,IncidentTypeCategory,ModifiedOnDateTime_dt",
            "returnGeometry":"true", "outSR":4326, "orderByFields":"OBJECTID",
            "resultOffset":page * PAGE_SIZE, "resultRecordCount":PAGE_SIZE})
        data = json.loads(_get(f"{NIFC_URL}?{query}"))
        for record in parse_nifc_page(data, at=at):
            records[record["official_id"]] = record
        if len(data["features"]) < PAGE_SIZE and not data.get("exceededTransferLimit"):
            return list(records.values())
    raise ValueError("NIFC pagination budget exceeded")


def build_snapshot(firms: dict[str, list[dict]], incidents: list[dict], *,
                   at: datetime, previous: dict | None = None,
                   errors: dict[str, str] | None = None) -> dict:
    at = _utc(at)
    errors = errors or {}
    cutoff = at - timedelta(hours=72)
    events = {}
    for event in (previous or {}).get("events", []):
        if datetime.fromisoformat(event["observed_at"]) >= cutoff:
            events[event["event_id"]] = event
    for items in firms.values():
        for item in items:
            old = events.get(item["event_id"])
            if old:
                item = {**item, "sources": sorted(set(item["sources"] + old["sources"])),
                        "detection_count": max(item["detection_count"], old["detection_count"])}
            events[item["event_id"]] = item
    sources = [{"key": source, "status": "failed" if source in errors else "complete",
                "last_attempt_at": at.isoformat(),
                "last_success_at": None if source in errors else at.isoformat(),
                "age_seconds": None if source in errors else 0}
               for source in FIRMS_SOURCES]
    sources.append({"key":"nifc_wfigs", "status":"failed" if "nifc_wfigs" in errors else "complete",
                    "last_attempt_at":at.isoformat(),
                    "last_success_at":None if "nifc_wfigs" in errors else at.isoformat(),
                    "age_seconds":None if "nifc_wfigs" in errors else 0})
    if errors and len(errors) == len(FIRMS_SOURCES) + 1:
        raise RuntimeError("all public sources failed; preserve last published snapshot")
    status = "partial" if errors else "fresh"
    event_list = sorted(events.values(), key=lambda item: item["observed_at"], reverse=True)
    return {"manifest":{"schema_version":1,"generated_at":at.isoformat(),
        "last_scan_at":at.isoformat(),"data_status":status,"candidate_count":len(event_list),
        "incident_count":len(incidents),"truncated":False,"source_errors":sorted(errors)},
        "events":event_list,"incidents":incidents,"matches":[],"sources":sources,"details":{}}
