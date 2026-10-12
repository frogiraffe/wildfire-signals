"""Offline prospective agency receipt import and as-of visibility.

An absent incident is only absent from a source layer, never labelled out.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .history import HistoryStore, _timestamp
from .history_pilot import CWFIS_RIGHTS, NIFC_RIGHTS
from .receipt_audit import _read

RIGHTS = {"cwfis": CWFIS_RIGHTS, "nifc_wfigs": NIFC_RIGHTS}
SOURCES = tuple(RIGHTS)


def _tables(store: HistoryStore) -> None:
    statements = ("""
        CREATE TABLE IF NOT EXISTS receipt_scans (
            scan_at TEXT PRIMARY KEY,
            captured_at TEXT NOT NULL,
            run_id TEXT NOT NULL,
            snapshot_key TEXT NOT NULL,
            receipt_sha256 TEXT NOT NULL
        )""", """
        CREATE INDEX IF NOT EXISTS receipt_scans_as_of
            ON receipt_scans(captured_at, scan_at)""", """
        CREATE TABLE IF NOT EXISTS receipt_sources (
            scan_at TEXT NOT NULL REFERENCES receipt_scans(scan_at),
            provider TEXT NOT NULL,
            status TEXT NOT NULL,
            PRIMARY KEY (scan_at, provider)
        )""", """
        CREATE TABLE IF NOT EXISTS receipt_presence (
            scan_at TEXT NOT NULL REFERENCES receipt_scans(scan_at),
            provider TEXT NOT NULL,
            official_id TEXT NOT NULL,
            agency_status TEXT,
            PRIMARY KEY (scan_at, provider, official_id)
        )""", """
        CREATE INDEX IF NOT EXISTS receipt_presence_identity
            ON receipt_presence(provider, official_id, scan_at)""")
    for statement in statements:
        store.connection.execute(statement)


def import_receipts(store: HistoryStore, directory: Path) -> dict:
    """Import verified artifacts transactionally; repeated files are harmless."""
    paths = sorted(Path(directory).rglob("agency-*.json.gz"))
    if not paths:
        raise ValueError("no agency receipts found")
    connection = store.connection
    caller_transaction = connection.in_transaction
    connection.execute("SAVEPOINT receipt_import")
    imported = 0
    seen_scans = set()
    try:
        _tables(store)
        for path in paths:
            receipt = _read(path)
            scan_at, captured_at = (_timestamp(receipt[key]) for key in
                                    ("scan_at", "captured_at"))
            if scan_at in seen_scans:
                raise ValueError("duplicate agency scan receipts")
            seen_scans.add(scan_at)
            states = receipt["source_states"]
            if set(states) != set(SOURCES):
                raise ValueError("incomplete agency source states")
            for provider in SOURCES:
                if states[provider]["status"] not in {"complete", "failed", "deferred"}:
                    raise ValueError("invalid agency source status")
            content_hash = hashlib.sha256(json.dumps(receipt, sort_keys=True,
                ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            provenance = (captured_at, receipt["run_id"], receipt["snapshot_key"],
                          content_hash)
            existing = connection.execute("""
                SELECT captured_at, run_id, snapshot_key, receipt_sha256
                FROM receipt_scans WHERE scan_at = ?
            """, (scan_at,)).fetchone()
            if existing:
                if tuple(existing) != provenance:
                    raise ValueError("conflicting agency scan receipt")
                continue
            connection.execute("""
                INSERT INTO receipt_scans
                (scan_at, captured_at, run_id, snapshot_key, receipt_sha256)
                VALUES (?, ?, ?, ?, ?)
            """, (scan_at, *provenance))
            imported += 1
            for provider in SOURCES:
                connection.execute("""
                    INSERT INTO receipt_sources (scan_at, provider, status) VALUES (?, ?, ?)
                """, (scan_at, provider, states[provider]["status"]))
            for incident in receipt["incidents"]:
                provider = incident["provider"]
                if states[provider]["status"] != "complete":
                    continue  # A failed fetch may carry a previous snapshot row.
                source_id = incident["official_id"]
                observed_at = incident.get("modified_at") or incident.get("last_seen_at")
                if not isinstance(source_id, str) or not source_id or not observed_at:
                    raise ValueError("agency incident identity or time missing")
                store.append({"subject_kind":"agency_incident", "provider":provider,
                              "source_id":source_id, "record_type":"incident_status",
                              "observed_at":observed_at, "captured_at":captured_at,
                              "source_url":("https://github.com/frogiraffe/wildfire-signals/"
                                            f"actions/runs/{receipt['run_id']}"),
                              "rights_url":RIGHTS[provider], "payload":incident},
                             commit=False)
                connection.execute("""
                    INSERT INTO receipt_presence
                    (scan_at, provider, official_id, agency_status) VALUES (?, ?, ?, ?)
                """, (scan_at, provider, source_id, incident.get("agency_status")))
        connection.execute("RELEASE SAVEPOINT receipt_import")
        if not caller_transaction:
            connection.commit()
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT receipt_import")
        connection.execute("RELEASE SAVEPOINT receipt_import")
        if not caller_transaction:
            connection.rollback()
        raise
    return {"schema_version": 1, "receipt_count": len(paths),
            "imported_scans": imported, "prediction": None,
            "extinguishment_labels_created": 0}


def incident_at(store: HistoryStore, provider: str, source_id: str, *, at: str) -> dict:
    """Describe source-layer visibility at a decision time, not fire outcome."""
    if provider not in SOURCES or not source_id:
        raise ValueError("agency identity required")
    cutoff = _timestamp(at)
    connection = store.connection
    scan = connection.execute("""
        SELECT s.scan_at, s.captured_at, r.status FROM receipt_scans s
        JOIN receipt_sources r ON r.scan_at = s.scan_at
        WHERE r.provider = ? AND s.captured_at <= ? AND s.scan_at <= ?
        ORDER BY s.captured_at DESC, s.scan_at DESC LIMIT 1
    """, (provider, cutoff, cutoff)).fetchone()
    last = connection.execute("""
        SELECT s.captured_at FROM receipt_presence p
        JOIN receipt_scans s ON s.scan_at = p.scan_at
        WHERE p.provider = ? AND p.official_id = ?
          AND s.captured_at <= ? AND s.scan_at <= ?
        ORDER BY s.captured_at DESC, s.scan_at DESC LIMIT 1
    """, (provider, source_id, cutoff, cutoff)).fetchone()
    result = {"provider": provider, "official_id": source_id, "as_of": cutoff,
              "last_listed_at": last["captured_at"] if last else None,
              "extinguishment_label": None, "prediction": None}
    if scan is None:
        return {**result, "availability": "no_receipt_yet", "source_status": None,
                "last_scan_at": None, "agency_status": None}
    result.update(source_status=scan["status"], last_scan_at=scan["scan_at"])
    if scan["status"] != "complete":
        return {**result, "availability": "source_unavailable", "agency_status": None}
    presence = connection.execute("""
        SELECT agency_status FROM receipt_presence
        WHERE scan_at = ? AND provider = ? AND official_id = ?
    """, (scan["scan_at"], provider, source_id)).fetchone()
    if presence is None:
        return {**result, "availability": "not_listed_in_complete_scan",
                "agency_status": None}
    return {**result, "availability": "listed", "agency_status": presence["agency_status"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Import verified prospective agency receipts")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--receipts", type=Path, required=True)
    args = parser.parse_args()
    store = HistoryStore(args.db)
    try:
        print(json.dumps(import_receipts(store, args.receipts), sort_keys=True))
    finally:
        store.close()


if __name__ == "__main__":
    main()
