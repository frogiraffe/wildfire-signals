"""Bounded, read-only US/Canada historical evidence pilot.

The selected records test storage and provenance, not predictive accuracy.
Historical provider dates are never treated as proof that data was available
to this application at those dates.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from .collect import CWFIS_URL, _get
from .history import HistoryStore

NIFC_PERIMETER_URL = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/ArcGIS/rest/"
                      "services/WFIGS_Interagency_Perimeters/FeatureServer/0/query")
CWFIS_RIGHTS = "https://cwfis.cfs.nrcan.gc.ca/downloads/licence.txt"
NIFC_RIGHTS = "https://www.nifc.gov/fire-information/maps"
CWFIS_IDS = ("0_SK_003464", "0_SK_003423")
NIFC_ID = "{EFB046E9-CE8C-4DE6-87A7-E824C33AE187}"


def cwfis_records(source: dict, *, expected_id: str, captured_at: str,
                  source_url: str) -> list[dict]:
    if source.get("type") != "FeatureCollection" or not isinstance(source.get("features"), list):
        raise ValueError("CWFIS history response unavailable")
    rows = []
    for feature in source["features"]:
        p = feature.get("properties") or {}
        if p.get("national_fire_id") != expected_id or not p.get("record_start"):
            raise ValueError("CWFIS history event mismatch")
        if p.get("stage_of_control_status") not in {"OC", "BH", "UC"}:
            raise ValueError("unexpected CWFIS status")
        rows.append({"subject_kind": "agency_incident", "provider": "cwfis",
                     "source_id": expected_id, "record_type": "incident_status",
                     "observed_at": p["record_start"], "captured_at": captured_at,
                     "source_url": source_url, "rights_url": CWFIS_RIGHTS,
                     "payload": {"stage_of_control_status": p["stage_of_control_status"],
                                 "record_end": p.get("record_end"),
                                 "fire_size": p.get("fire_size"),
                                 "latitude": p.get("latitude"),
                                 "longitude": p.get("longitude"),
                                 "evidence_role": "retrospective_history"}})
    if not rows:
        raise ValueError("CWFIS history event missing")
    return sorted(rows, key=lambda row: row["observed_at"])


def nifc_perimeter_record(source: dict, *, expected_id: str, captured_at: str,
                          source_url: str) -> dict:
    features = source.get("features")
    if source.get("error") or not isinstance(features, list) or len(features) != 1:
        raise ValueError("NIFC perimeter response incomplete or ambiguous")
    feature = features[0]
    p, geometry = feature.get("attributes") or {}, feature.get("geometry") or {}
    if (p.get("poly_IRWINID") != expected_id or p.get("attr_IncidentTypeCategory") != "WF"
            or not isinstance(geometry.get("rings"), list) or not geometry["rings"]):
        raise ValueError("NIFC perimeter identity or geometry unavailable")
    stamp = p.get("poly_PolygonDateTime")
    if not isinstance(stamp, (int, float)) or not stamp:
        raise ValueError("NIFC perimeter date unavailable")
    observed = datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat()
    return {"subject_kind": "agency_incident", "provider": "nifc_wfigs",
            "source_id": expected_id, "record_type": "perimeter_observation",
            "observed_at": observed, "captured_at": captured_at,
            "source_url": source_url, "rights_url": NIFC_RIGHTS,
            "payload": {"name": p.get("poly_IncidentName"),
                        "geometry_format": "esri_json_epsg4326", "geometry": geometry,
                        "fire_out_at_provider": p.get("attr_FireOutDateTime"),
                        "perimeter_role": "retrospective_outcome"}}


def _fetch_json(url: str) -> tuple[dict, bytes]:
    raw = _get(url)
    return json.loads(raw), raw


def _received_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_pilot(db_path: Path, raw_dir: Path) -> dict:
    if db_path.exists() or (raw_dir / "pilot-manifest.json").exists():
        raise FileExistsError("pilot output already exists; choose a new path")
    started_at = _received_at()
    raw_dir.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 2, "started_at": started_at, "samples": [],
              "predictive_evidence": False}
    with_history = HistoryStore(db_path)
    try:
        for fire_id in CWFIS_IDS:
            query = urlencode({"service": "WFS", "version": "2.0.0",
                "request": "GetFeature", "typeName": "public:cwfif_national_activefires",
                "count": 10, "outputFormat": "application/json", "sortBy": "record_start",
                "cql_filter": f"national_fire_id='{fire_id}'"})
            url = f"{CWFIS_URL}?{query}"
            source, raw = _fetch_json(url)
            captured_at = _received_at()
            if int(source.get("numberMatched", 0)) > len(source.get("features", [])):
                raise ValueError("CWFIS pilot response truncated")
            records = cwfis_records(source, expected_id=fire_id,
                                    captured_at=captured_at, source_url=url)
            raw_hash = hashlib.sha256(raw).hexdigest()
            (raw_dir / f"{raw_hash}.json.gz").write_bytes(gzip.compress(raw, mtime=0))
            for record in records:
                with_history.append(record)
            report["samples"].append({"event_key": f"cwfis:{fire_id}",
                "record_count": len(records), "captured_at": captured_at,
                "source_response_sha256": raw_hash,
                "source_url": url, "source_bytes": len(raw),
                "history_kind": "provider_status_intervals"})

        query = urlencode({"f": "json", "where": f"poly_IRWINID='{NIFC_ID}'",
            "outFields": "poly_IRWINID,poly_IncidentName,poly_PolygonDateTime,attr_FireOutDateTime,attr_IncidentTypeCategory",
            "returnGeometry": "true", "outSR": 4326, "resultRecordCount": 2})
        url = f"{NIFC_PERIMETER_URL}?{query}"
        source, raw = _fetch_json(url)
        captured_at = _received_at()
        record = nifc_perimeter_record(source, expected_id=NIFC_ID,
                                       captured_at=captured_at, source_url=url)
        raw_hash = hashlib.sha256(raw).hexdigest()
        (raw_dir / f"{raw_hash}.json.gz").write_bytes(gzip.compress(raw, mtime=0))
        with_history.append(record)
        report["samples"].append({"event_key": f"nifc_wfigs:{NIFC_ID}",
            "record_count": 1, "captured_at": captured_at,
            "source_response_sha256": raw_hash,
            "source_url": url, "source_bytes": len(raw),
            "history_kind": "retrospective_perimeter_only"})
    finally:
        with_history.close()
    report["sqlite_bytes"] = db_path.stat().st_size
    report["compressed_raw_bytes"] = sum(x.stat().st_size for x in raw_dir.glob("*.json.gz"))
    (raw_dir / "pilot-manifest.json").write_text(
        json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return report


def replay_pilot(raw_dir: Path, db_path: Path) -> dict:
    """Rebuild pilot DB from checksum-verified source responses, without network."""
    if db_path.exists():
        raise FileExistsError("replay database already exists")
    manifest = json.loads((raw_dir / "pilot-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version", 1) not in (1, 2):
        raise ValueError("unsupported pilot manifest")
    prepared = []
    for sample in manifest["samples"]:
        digest = sample["source_response_sha256"]
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("invalid source checksum")
        raw = gzip.decompress((raw_dir / f"{digest}.json.gz").read_bytes())
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("source checksum mismatch")
        source = json.loads(raw)
        key = sample["event_key"]
        # Version 1 stored only a run-start estimate; preserve its original
        # replay result, but use per-response receipt times for new manifests.
        captured_at = (sample["captured_at"] if manifest.get("schema_version") == 2
                       else manifest["captured_at"])
        if key.startswith("cwfis:"):
            records = cwfis_records(source, expected_id=key.removeprefix("cwfis:"),
                                    captured_at=captured_at,
                                    source_url=sample["source_url"])
        elif key == f"nifc_wfigs:{NIFC_ID}":
            records = [nifc_perimeter_record(source, expected_id=NIFC_ID,
                captured_at=captured_at,
                source_url=sample["source_url"])]
        else:
            raise ValueError("unsupported pilot event")
        if len(records) != sample["record_count"]:
            raise ValueError("source record count changed")
        prepared.extend(records)
    store = HistoryStore(db_path)
    try:
        for record in prepared:
            store.append(record)
    finally:
        store.close()
    return {"restored_records": len(prepared), "sqlite_bytes": db_path.stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded official history data pilot")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--replay", action="store_true", help="rebuild from saved responses")
    args = parser.parse_args()
    result = replay_pilot(args.raw_dir, args.db) if args.replay else run_pilot(args.db, args.raw_dir)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
