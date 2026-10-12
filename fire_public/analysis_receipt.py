"""Bounded prospective agency evidence from an already published snapshot."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from .history import _timestamp

MAX_INCIDENTS = 2000
MAX_COMPRESSED_BYTES = 128 * 1024
AGENCY_SOURCES = ("nifc_wfigs", "cwfis")
INCIDENT_FIELDS = ("kind", "provider", "official_id", "name", "incident_kind",
                   "latitude", "longitude", "modified_at", "agency_status", "last_seen_at")


def build_receipt(snapshot: dict, *, captured_at: str, run_id: str,
                  head_sha: str, snapshot_key: str) -> tuple[bytes, dict]:
    manifest = snapshot.get("manifest") if isinstance(snapshot, dict) else None
    if (not isinstance(manifest, dict) or manifest.get("schema_version") != 1
            or manifest.get("truncated") is not False):
        raise ValueError("complete public snapshot required")
    scan_at, captured = _timestamp(manifest.get("last_scan_at")), _timestamp(captured_at)
    if scan_at > captured:
        raise ValueError("scan cannot postdate receipt")
    if (not re.fullmatch(r"[1-9]\d*", str(run_id)) or
            not re.fullmatch(r"[a-f0-9]{40}", head_sha) or
            not re.fullmatch(r"snapshot:[a-f0-9]{64}", snapshot_key)):
        raise ValueError("invalid hosted run provenance")
    source_rows = snapshot.get("sources")
    if not isinstance(source_rows, list):
        raise ValueError("source states unavailable")
    source_states = {}
    for key in AGENCY_SOURCES:
        matches = [row for row in source_rows if isinstance(row, dict) and row.get("key") == key]
        if len(matches) != 1 or matches[0].get("status") not in {"complete", "failed", "deferred"}:
            raise ValueError("agency source state unavailable")
        row = matches[0]
        source_states[key] = {field: row.get(field) for field in
                              ("status", "last_success_at", "last_product_observed_at",
                               "consecutive_failures")}
    source_incidents = snapshot.get("incidents")
    if not isinstance(source_incidents, list) or len(source_incidents) > MAX_INCIDENTS:
        raise ValueError("agency incident cohort exceeds pilot limit")
    incidents, identities = [], set()
    for row in source_incidents:
        if (not isinstance(row, dict) or row.get("kind") != "agency_incident" or
                row.get("provider") not in AGENCY_SOURCES or
                not isinstance(row.get("official_id"), str) or not row["official_id"]):
            raise ValueError("invalid agency incident")
        identity = row["provider"], row["official_id"]
        if identity in identities:
            raise ValueError("duplicate agency incident")
        identities.add(identity)
        for coordinate, lower, upper in (("latitude", -90, 90), ("longitude", -180, 180)):
            value = row.get(coordinate)
            if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                    not math.isfinite(value) or not lower <= value <= upper):
                raise ValueError("invalid agency location")
        for field in ("modified_at", "last_seen_at"):
            value = row.get(field)
            if value is not None and _timestamp(value) > captured:
                raise ValueError("agency time postdates receipt")
        incidents.append({field: row.get(field) for field in INCIDENT_FIELDS})
    incidents.sort(key=lambda row: (row["provider"], row["official_id"]))
    receipt = {"schema_version": 1, "evidence_role": "prospective_agency_receipt",
               "scan_at": scan_at, "captured_at": captured,
               "run_id": str(run_id), "head_sha": head_sha,
               "snapshot_key": snapshot_key,
               "snapshot_status": manifest.get("data_status"),
               "source_errors": manifest.get("source_errors", []),
               "source_states": source_states, "incident_count": len(incidents),
               "incidents": incidents}
    raw = json.dumps(receipt, sort_keys=True, ensure_ascii=False, allow_nan=False,
                     separators=(",", ":")).encode()
    compressed = gzip.compress(raw, compresslevel=6, mtime=0)
    if len(compressed) > MAX_COMPRESSED_BYTES:
        raise ValueError("agency receipt exceeds artifact budget")
    return compressed, {"incident_count": len(incidents),
                        "compressed_bytes": len(compressed), "scan_at": scan_at}


def write_receipt(directory: Path, payload: bytes, *, scan_at: str) -> Path:
    stamp = datetime.fromisoformat(_timestamp(scan_at)).strftime("%Y%m%dT%H%M%S%fZ")
    digest = hashlib.sha256(payload).hexdigest()[:16]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"agency-{stamp}-{digest}.json.gz"
    descriptor, temporary = tempfile.mkstemp(prefix=".agency-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, path)  # Fails if a prior receipt already owns this name.
        return path
    finally:
        Path(temporary).unlink(missing_ok=True)
