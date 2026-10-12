"""Small *live-provider* contract audit for the official historical NIFC layer.

Unlike unit fixtures, this CLI makes three read-only HTTP requests: layer
metadata, official year-specific ID list, and one GeoJSON polygon. The exact
source schema and downloaded polygon are audited and retained locally.
No non-fire labels, prospective features, model probabilities, or cloud writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, build_opener

from .official_perimeters import (
    SERVICE, RIGHTS_URL, _RejectRedirects, _canonical, report, sync_year,
)

EXPECTED_ITEM_ID = "e02b85c0ea784ce7bd8add7ae3d293d0"
MAX_METADATA_BYTES = 1024 * 1024
REQUIRED_FIELDS = frozenset({
    "OBJECTID", "GlobalID", "FIRE_YEAR_INT", "INCIDENT", "GIS_ACRES",
})


def _get_layer_metadata() -> dict:
    url = SERVICE + "?f=json"
    request = Request(url, headers={
        "User-Agent": "WildfireSignals-OfficialProviderAudit/1",
        "Accept": "application/json",
    })
    with build_opener(_RejectRedirects()).open(request, timeout=30) as response:
        raw = response.read(MAX_METADATA_BYTES + 1)
    if len(raw) > MAX_METADATA_BYTES:
        raise ValueError("NIFC layer metadata exceeds bounded response budget")
    return json.loads(raw)


def validate_layer_metadata(metadata: dict) -> dict:
    """Fail closed if an endpoint was silently replaced or its API schema drifted."""
    if not isinstance(metadata, dict) or metadata.get("error"):
        raise ValueError("NIFC layer metadata unavailable")
    checks = {
        "official_service_item": metadata.get("serviceItemId") == EXPECTED_ITEM_ID,
        "historical_layer_id": metadata.get("id") == 0,
        "polygon_geometry": metadata.get("geometryType") == "esriGeometryPolygon",
        "official_object_id": metadata.get("objectIdField") == "OBJECTID",
        "official_global_id": metadata.get("globalIdField") == "GlobalID",
        "geojson_query_supported": "geojson" in str(
            metadata.get("supportedQueryFormats", "")).casefold(),
        "read_only_query_available": "Query" in str(metadata.get("capabilities", "")),
    }
    fields = metadata.get("fields")
    keys = {r.get("name") for r in fields if isinstance(r, dict)} if isinstance(fields, list) else set()
    checks["source_fields_present"] = REQUIRED_FIELDS.issubset(keys)
    if not all(checks.values()):
        failed = sorted(k for k, ok in checks.items() if not ok)
        raise ValueError("official ArcGIS layer contract drift: " + ", ".join(failed))
    # Protect output from huge copied service metadata; retain versioned SHA-256
    # and only the schema facts actually used by this ingestion workflow.
    schema_fields = sorted(
        (r["name"], r.get("type", ""))
        for r in fields if isinstance(r, dict) and isinstance(r.get("name"), str))
    return {
        "service": SERVICE,
        "service_item_id": EXPECTED_ITEM_ID,
        "schema_sha256": hashlib.sha256(_canonical(metadata).encode()).hexdigest(),
        "field_schema": schema_fields,
        "query_max_record_count": metadata.get("maxRecordCount"),
        "last_source_data_edit_ms": (metadata.get("editingInfo") or {}).get("dataLastEditDate"),
        "assertions": checks,
    }


def live_sample_probe(
        db_path: str | Path,
        *, year: int = 2018,
        fetch_metadata=_get_layer_metadata,
        get_json=None,
        clock=None,
) -> dict:
    """Verify one actual source record and expose repeatable evidence, not skill.

    Callers/tests can inject HTTP functions, but production CLI uses fixed NIFC
    endpoints only. Result metadata is useful for a live CI artifact and manual
    local field/schema compatibility investigations.
    """
    metadata = validate_layer_metadata(fetch_metadata())
    if get_json is None:
        from .official_perimeters import _fetch
        get_json = _fetch
    captured = clock() if clock is not None else datetime.now(timezone.utc).isoformat()
    import_result = sync_year(db_path, year=year, max_records=1, get_json=get_json,
                              clock=lambda: captured)
    if import_result["fetched_perimeters"] != 1:
        raise ValueError("official historical year has no sample perimeter to verify")
    evaluated = report(db_path, at=captured, year=year, limit=1)
    if evaluated["shown"] != 1:
        raise ValueError("retrieved official perimeter unavailable in as-of SQLite report")
    event = evaluated["events"][0]
    if (event["source_attributes"].get("OBJECTID") != event["object_id"]
            or event["source_attributes"].get("FIRE_YEAR_INT") != year
            or event["geometry"]["type"] not in ("Polygon", "MultiPolygon")):
        raise ValueError("stored official source properties contradict validated geometry")
    return {
        "schema_version": 1,
        "status": "live_provider_contract_verified",
        "provider": "nifc_interagency_fire_perimeter_history",
        "source_url": SERVICE,
        "rights_url": RIGHTS_URL,
        "query_year": year,
        "source_metadata": metadata,
        "verified_retrieved_records": 1,
        "retrieval": import_result,
        "stored_feature": {
            "object_id": event["object_id"],
            "source_identity": event["source_identity"],
            "fire_year": event["fire_year"],
            "feature_sha256": event["feature_sha256"],
            "captured_at": event["captured_at"],
            "batch_id": event["batch_id"],
            "geometry_type": event["geometry"]["type"],
            "original_attribute_count": len(event["source_attributes"]),
            "source_reported_acres": event["source_reported_acres"],
        },
        "negative_labels_created": 0,
        "model_ready": False,
        "evidence_incomplete": True,
        "caveats": [
            "This verifies one real source response, not a complete fire-year census.",
            "Historical official geometry is retrospective evidence, not a prospective predictor.",
            "A missing perimeter is never an independent negative wildfire label.",
            "Provider and transport compatibility at this time do not establish future availability.",
        ],
    }


def _write_json_new(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as target:
        json.dump(data, target, sort_keys=True, indent=2, ensure_ascii=False,
                  allow_nan=False)
        target.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check NIFC real public historical perimeter API with 1 record")
    parser.add_argument("--db", type=Path, required=True,
                        help="private local versioned perimeter archive")
    parser.add_argument("--year", type=int, default=2018)
    parser.add_argument("--output", type=Path, required=True,
                        help="new source-contract verification report JSON")
    args = parser.parse_args()
    if (args.output.resolve() == args.db.resolve()
            or args.output.exists()):
        parser.error("output must be new and cannot overwrite input archive")
    result = live_sample_probe(args.db, year=args.year)
    _write_json_new(args.output, result)
    print(json.dumps({
        "status": result["status"],
        "provider": result["provider"],
        "year": result["query_year"],
        "verified_retrieved_records": result["verified_retrieved_records"],
        "metadata_sha256": result["source_metadata"]["schema_sha256"],
        "report": str(args.output),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
