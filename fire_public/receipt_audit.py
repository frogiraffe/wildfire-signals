"""Offline audit of temporary GitHub agency research receipts."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from .analysis_receipt import MAX_COMPRESSED_BYTES
from .history import _timestamp

NAME = re.compile(r"agency-(\d{8}T\d{12}Z)-([a-f0-9]{16})\.json\.gz$")
MAX_RAW_BYTES = 2 * 1024 * 1024


def _read(path: Path) -> dict:
    match = NAME.fullmatch(path.name)
    with path.open("rb") as source:
        raw = source.read(MAX_COMPRESSED_BYTES + 1)
    if (not match or len(raw) > MAX_COMPRESSED_BYTES or
            hashlib.sha256(raw).hexdigest()[:16] != match.group(2)):
        raise ValueError("agency receipt checksum or size mismatch")
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
        content = compressed.read(MAX_RAW_BYTES + 1)
    if len(content) > MAX_RAW_BYTES:
        raise ValueError("agency receipt decompressed budget exceeded")
    receipt = json.loads(content)
    if receipt.get("schema_version") != 1 or receipt.get("evidence_role") != "prospective_agency_receipt":
        raise ValueError("unsupported agency receipt")
    scan_at, captured_at = _timestamp(receipt["scan_at"]), _timestamp(receipt["captured_at"])
    if (scan_at > captured_at or datetime.fromisoformat(scan_at).strftime(
            "%Y%m%dT%H%M%S%fZ") != match.group(1)):
        raise ValueError("agency receipt time mismatch")
    incidents = receipt.get("incidents")
    if (not isinstance(incidents, list) or len(incidents) != receipt.get("incident_count")
            or len(incidents) > 2000 or any(row.get("kind") != "agency_incident"
                                          for row in incidents if isinstance(row, dict))
            or any(not isinstance(row, dict) for row in incidents)):
        raise ValueError("agency receipt cohort invalid")
    identities = [(row.get("provider"), row.get("official_id")) for row in incidents]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate agency identity in receipt")
    return receipt


def audit_receipts(directory: Path) -> dict:
    paths = sorted(directory.rglob("agency-*.json.gz"))
    if not paths:
        raise ValueError("no agency receipts found")
    receipts = [_read(path) for path in paths]
    receipts.sort(key=lambda row: row["scan_at"])
    scan_times = [datetime.fromisoformat(_timestamp(row["scan_at"])) for row in receipts]
    if len(scan_times) != len(set(scan_times)):
        raise ValueError("duplicate agency scan receipts")
    gaps = [{"from": first.isoformat(), "to": second.isoformat(),
             "hours": round((second - first).total_seconds() / 3600, 3)}
            for first,second in zip(scan_times,scan_times[1:])
            if (second - first).total_seconds() > 9 * 3600]
    failures = Counter()
    deferrals = Counter()
    identities = Counter()
    for receipt in receipts:
        states = receipt.get("source_states")
        if not isinstance(states, dict):
            raise ValueError("agency source states missing")
        for source in ("nifc_wfigs", "cwfis"):
            state = states.get(source)
            if not isinstance(state, dict) or state.get("status") not in {
                    "complete", "failed", "deferred"}:
                raise ValueError("agency source state invalid")
            if state["status"] == "failed":
                failures[source] += 1
            elif state["status"] == "deferred":
                deferrals[source] += 1
        for incident in receipt["incidents"]:
            provider, source_id = incident.get("provider"), incident.get("official_id")
            if provider not in {"nifc_wfigs", "cwfis"} or not isinstance(source_id, str):
                raise ValueError("agency receipt identity invalid")
            identities[(provider,source_id)] += 1
    return {"schema_version": 1, "receipt_count": len(receipts),
            "first_scan_at": scan_times[0].isoformat(),
            "last_scan_at": scan_times[-1].isoformat(),
            "gaps_over_9_hours": gaps,
            "source_failure_counts": dict(sorted(failures.items())),
            "source_deferred_counts": dict(sorted(deferrals.items())),
            "distinct_agency_identities": len(identities),
            "identities_seen_in_2_or_more_receipts": sum(count >= 2 for count in identities.values()),
            "extinguishment_labels_created": 0,
            "warning": "Disappearance from a current source is not an extinguishment label."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit downloaded agency receipt artifacts")
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_receipts(args.directory),sort_keys=True))


if __name__ == "__main__":
    main()
