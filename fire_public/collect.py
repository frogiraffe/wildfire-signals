"""Bounded global NASA FIRMS candidates and separate NIFC agency incidents."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FIRMS_SOURCES = ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")
FIRMS_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv/{key}/{source}/world/4"
NIFC_URL = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
            "WFIGS_Incident_Locations_Current/FeatureServer/0/query")
CWFIS_URL = "https://geoserver.cwfif.nrcan.gc.ca/geoserver/ows"
MAX_RESPONSE_BYTES = 50 * 1024 * 1024
MAX_CSV_ROWS = 250_000
MAX_NIFC_PAGES = 10
PAGE_SIZE = 1000
MAX_TIMELINE_INCIDENTS = 2000


class SourceDeferred(RuntimeError):
    """Upstream quota or throttling; collection should preserve prior data."""


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
                or observed < at - timedelta(hours=72)):
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
    try:
        with urlopen(Request(url, headers={"User-Agent":"WildfireSignals/0.1 (+https://github.com/frogiraffe/wildfire-signals)"}),
                     timeout=45) as response:
            if response.status != 200:
                raise RuntimeError(f"upstream HTTP {response.status}")
            data = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 429:
            raise SourceDeferred("upstream rate limited") from None
        raise
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


def parse_cwfis_page(raw: dict, *, at: datetime) -> list[dict]:
    if raw.get("type") != "FeatureCollection" or not isinstance(raw.get("features"), list):
        raise ValueError("CWFIS response schema unavailable")
    records = []
    for feature in raw["features"]:
        properties = feature.get("properties") or {}
        official_id = properties.get("national_fire_id")
        if not official_id or properties.get("stage_of_control_status") not in {"OC", "BH", "UC"}:
            continue
        try:
            lat, lon = float(properties["latitude"]), float(properties["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            continue
        records.append({"kind":"agency_incident", "provider":"cwfis",
            "official_id":str(official_id), "name":str(properties.get("agency_fire_id") or "")[:100],
            "incident_kind":"active_wildland_fire", "latitude":lat, "longitude":lon,
            "modified_at":properties.get("status_date"),
            "agency_status":properties["stage_of_control_status"],
            "last_seen_at":_utc(at).isoformat()})
    return records


def fetch_cwfis(*, at: datetime) -> list[dict]:
    """Query active time slice, never the entire historical WFS layer."""
    at = _utc(at)
    stamp = at.strftime("%Y-%m-%dT%H:%M:%SZ")
    cql = (f"record_end > '{stamp}' AND record_start <= '{stamp}' "
           "AND stage_of_control_status IN ('OC','BH','UC')")
    records = {}
    for page in range(MAX_NIFC_PAGES):
        query = urlencode({"service":"WFS", "version":"2.0.0", "request":"GetFeature",
            "typeName":"public:cwfif_national_activefires", "count":PAGE_SIZE,
            "startIndex":page * PAGE_SIZE, "sortBy":"national_fire_id",
            "outputFormat":"application/json", "cql_filter":cql})
        data = json.loads(_get(f"{CWFIS_URL}?{query}"))
        for item in parse_cwfis_page(data, at=at):
            records[item["official_id"]] = item
        if len(data["features"]) < PAGE_SIZE:
            matched = data.get("numberMatched")
            if isinstance(matched, int) and matched > (page + 1) * PAGE_SIZE:
                raise ValueError("CWFIS response incomplete")
            return list(records.values())
    raise ValueError("CWFIS pagination budget exceeded")


def provisional_matches(events: list[dict], incidents: list[dict]) -> list[dict]:
    """Nearby points only; never a fire confirmation or shared identity."""
    index: dict[tuple[int, int], list[dict]] = {}
    for item in incidents:
        try:
            modified = datetime.fromisoformat(item["modified_at"])
            if modified.tzinfo is None or modified.utcoffset() is None:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        cell = (math.floor(item["latitude"] * 10), math.floor(item["longitude"] * 10))
        index.setdefault(cell, []).append(item)
    matches = []
    for event in events:
        lat, lon = event["latitude"], event["longitude"]
        cell = (math.floor(lat * 10), math.floor(lon * 10))
        nearby = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for incident in index.get((cell[0] + dy, cell[1] + dx), []):
                    try:
                        observed = datetime.fromisoformat(event["observed_at"])
                        modified = datetime.fromisoformat(incident["modified_at"])
                        delta = observed - modified
                        if not -timedelta(hours=24) <= delta <= timedelta(hours=72):
                            continue
                    except (KeyError, TypeError, ValueError):
                        continue
                    phi1, phi2 = math.radians(lat), math.radians(incident["latitude"])
                    delta_phi = phi2 - phi1
                    delta_lon = math.radians(incident["longitude"] - lon)
                    h = math.sin(delta_phi / 2) ** 2 + (math.cos(phi1) * math.cos(phi2)
                        * math.sin(delta_lon / 2) ** 2)
                    distance = 12742.0176 * math.asin(math.sqrt(min(1, h)))
                    if distance <= 8:
                        nearby.append((incident, distance))
        for incident, distance in nearby:
            matches.append({"event_id":event["event_id"], "provider":incident["provider"],
                "official_id":incident["official_id"],
                "status":"ambiguous" if len(nearby) > 1 else "provisional",
                "method":"cell_center_distance_v1", "distance_km":round(distance, 2)})
    return matches


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
    prior_sources = {row["key"]: row for row in (previous or {}).get("sources", [])}
    sources = []
    for source in (*FIRMS_SOURCES, "nifc_wfigs", "cwfis"):
        failed = source in errors
        prior = prior_sources.get(source, {})
        success = prior.get("last_success_at") if failed else at.isoformat()
        success_at = datetime.fromisoformat(success) if success else None
        observations = (firms.get(source, []) if source in FIRMS_SOURCES else
                        [item for item in incidents if item.get("provider") == source])
        product = max((item.get("observed_at") or item.get("modified_at") or ""
                       for item in observations), default="") if not failed else ""
        product = product or prior.get("last_product_observed_at")
        product_at = datetime.fromisoformat(product) if product else None
        state = ("deferred" if errors.get(source) == "SourceDeferred" else "failed") if failed else "complete"
        sources.append({"key":source, "status":state,
                        "last_attempt_at":at.isoformat(), "last_success_at":success,
                        "age_seconds":max(0,int((at - success_at).total_seconds())) if success_at else None,
                        "last_product_observed_at":product,
                        "product_age_seconds":max(0,int((at - product_at).total_seconds()))
                        if product_at else None,
                        "consecutive_failures":prior.get("consecutive_failures",0) + 1
                        if failed else 0})
    if errors and len(errors) == len(FIRMS_SOURCES) + 2:
        raise RuntimeError("all public sources failed; preserve last published snapshot")
    prior_history = ((previous or {}).get("details") or {}).get("incident_history") or {}
    history = {}
    for incident in incidents:
        key = f"{incident['provider']}:{incident['official_id']}"
        entries = [row for row in prior_history.get(key, [])
                   if isinstance(row, dict) and row.get("seen_at", "") >= cutoff.isoformat()]
        status = incident.get("agency_status")
        source_modified = incident.get("modified_at")
        if not entries or (entries[-1].get("agency_status") != status
                           or entries[-1].get("source_modified_at") != source_modified):
            entries.append({"change": "record_changed" if entries else "first_seen",
                            "seen_at": at.isoformat(), "source_modified_at": source_modified,
                            "agency_status": status})
        history[key] = entries[-5:]
    for key, entries in prior_history.items():
        provider = key.split(":", 1)[0]
        if key not in history and provider in errors:
            valid = [row for row in entries if isinstance(row, dict)
                     and row.get("seen_at", "") >= cutoff.isoformat()]
            if valid:
                history[key] = valid[-5:]
    if len(history) > MAX_TIMELINE_INCIDENTS:
        recent_keys = sorted(history, key=lambda key: (history[key][-1]["seen_at"], key),
                             reverse=True)[:MAX_TIMELINE_INCIDENTS]
        history = {key: history[key] for key in recent_keys}
    status = "partial" if errors else "fresh"
    event_list = sorted(events.values(), key=lambda item: item["observed_at"], reverse=True)
    return {"manifest":{"schema_version":1,"generated_at":at.isoformat(),
        "last_scan_at":at.isoformat(),"data_status":status,"candidate_count":len(event_list),
        "incident_count":len(incidents),"truncated":False,"source_errors":sorted(errors)},
        "events":event_list,"incidents":incidents,
        "matches":provisional_matches(event_list, incidents),"sources":sources,
        "details":{"incident_history":history}}
