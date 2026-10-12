"""Append-only, locally reproducible evidence archive for historical analysis.

This module does not publish data or equate a satellite candidate with a fire.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _timestamp(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("invalid timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed.astimezone(timezone.utc).isoformat()


def _fire_event_id(provider: str, source_id: str) -> str:
    identity = json.dumps([provider, source_id], separators=(",", ":"))
    return "fire_event:" + hashlib.sha256(identity.encode()).hexdigest()[:24]


class HistoryStore:
    """A small pilot archive. Never place its database in Git or Workers KV."""

    def __init__(self, path: str | Path):
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY,
                subject_kind TEXT NOT NULL,
                event_key TEXT NOT NULL,
                provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                record_type TEXT NOT NULL,
                observed_at TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                source_url TEXT NOT NULL,
                rights_url TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
        """)
        self.connection.execute("""
            CREATE INDEX IF NOT EXISTS observations_as_of
            ON observations(event_key, captured_at)
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS fire_events (
                event_id TEXT PRIMARY KEY,
                first_captured_at TEXT NOT NULL
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS fire_event_sources (
                provider TEXT NOT NULL,
                source_id TEXT NOT NULL,
                event_id TEXT NOT NULL REFERENCES fire_events(event_id),
                first_captured_at TEXT NOT NULL,
                PRIMARY KEY (provider, source_id)
            )
        """)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS scan_runs (
                id TEXT PRIMARY KEY,
                scan_at TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                source_url TEXT NOT NULL,
                manifest_json TEXT NOT NULL
            )
        """)
        if self.connection.execute("PRAGMA user_version").fetchone()[0] < 1:
            # Pilot archives created before event identities can be opened directly.
            old_sources = self.connection.execute("""
                SELECT provider, source_id, MIN(captured_at) AS first_captured_at
                FROM observations WHERE subject_kind = 'agency_incident'
                GROUP BY provider, source_id
            """).fetchall()
            for row in old_sources:
                event_id = _fire_event_id(row["provider"], row["source_id"])
                self.connection.execute("""
                    INSERT OR IGNORE INTO fire_events (event_id, first_captured_at) VALUES (?, ?)
                """, (event_id, row["first_captured_at"]))
                self.connection.execute("""
                    INSERT OR IGNORE INTO fire_event_sources
                    (provider, source_id, event_id, first_captured_at) VALUES (?, ?, ?, ?)
                """, (row["provider"], row["source_id"], event_id, row["first_captured_at"]))
            self.connection.execute("PRAGMA user_version = 1")
            self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def append(self, record: dict, *, commit: bool = True) -> str:
        required = ("subject_kind", "provider", "source_id", "record_type",
                    "observed_at", "captured_at", "source_url", "rights_url", "payload")
        if any(key not in record for key in required):
            raise ValueError("incomplete observation")
        if record["subject_kind"] not in {"agency_incident", "satellite_candidate",
                                          "weather_forecast_snapshot"}:
            raise ValueError("unsupported subject kind")
        if any(not isinstance(record[key], str) or not record[key].strip()
               for key in ("provider", "source_id", "record_type", "source_url", "rights_url")):
            raise ValueError("source identity and rights required")
        observed, captured = _timestamp(record["observed_at"]), _timestamp(record["captured_at"])
        if observed > captured:
            raise ValueError("observation cannot postdate capture")
        payload = json.dumps(record["payload"], ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"), allow_nan=False)
        identity = {"subject_kind": record["subject_kind"], "provider": record["provider"],
                    "source_id": record["source_id"], "record_type": record["record_type"],
                    "observed_at": observed, "source_url": record["source_url"],
                    "rights_url": record["rights_url"], "payload": json.loads(payload)}
        digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                                           separators=(",", ":")).encode()).hexdigest()
        event_key = f"{record['provider']}:{record['source_id']}"
        started_transaction = not self.connection.in_transaction
        if started_transaction:
            self.connection.execute("BEGIN")
        self.connection.execute("SAVEPOINT append_record")
        try:
            self.connection.execute("""
                INSERT OR IGNORE INTO observations
                (id, subject_kind, event_key, provider, source_id, record_type,
                 observed_at, captured_at, source_url, rights_url, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (digest, record["subject_kind"], event_key, record["provider"],
                  record["source_id"], record["record_type"], observed, captured,
                  record["source_url"], record["rights_url"], payload))
            if record["subject_kind"] == "agency_incident":
                # A source-specific event is a stable anchor, not proof that another
                # provider or a nearby satellite cell describes the same fire.
                event_id = _fire_event_id(record["provider"], record["source_id"])
                self.connection.execute("""
                    INSERT INTO fire_events (event_id, first_captured_at) VALUES (?, ?)
                    ON CONFLICT(event_id) DO UPDATE SET
                        first_captured_at = MIN(first_captured_at, excluded.first_captured_at)
                """, (event_id, captured))
                self.connection.execute("""
                    INSERT INTO fire_event_sources
                    (provider, source_id, event_id, first_captured_at) VALUES (?, ?, ?, ?)
                    ON CONFLICT(provider, source_id) DO UPDATE SET
                        first_captured_at = MIN(first_captured_at, excluded.first_captured_at)
                """, (record["provider"], record["source_id"], event_id, captured))
        except Exception:
            self.connection.execute("ROLLBACK TO SAVEPOINT append_record")
            self.connection.execute("RELEASE SAVEPOINT append_record")
            if started_transaction:
                self.connection.rollback()
            raise
        self.connection.execute("RELEASE SAVEPOINT append_record")
        if commit:
            self.connection.commit()
        return digest

    def fire_event_for(self, provider: str, source_id: str, *, at: str | None = None) -> str | None:
        """Find the agency incident's event; candidate observations have no automatic link."""
        cutoff = _timestamp(at) if at is not None else None
        row = self.connection.execute("""
            SELECT event_id FROM fire_event_sources
            WHERE provider = ? AND source_id = ? AND (? IS NULL OR first_captured_at <= ?)
        """, (provider, source_id, cutoff, cutoff)).fetchone()
        return row["event_id"] if row else None

    def as_of_event(self, at: str, event_id: str) -> list[dict]:
        cutoff = _timestamp(at)
        rows = self.connection.execute("""
            SELECT o.* FROM observations o
            JOIN fire_event_sources s ON s.provider = o.provider AND s.source_id = o.source_id
            WHERE s.event_id = ? AND s.first_captured_at <= ?
              AND o.subject_kind = 'agency_incident'
              AND o.captured_at <= ? AND o.observed_at <= ?
            ORDER BY o.captured_at, o.observed_at, o.id
        """, (event_id, cutoff, cutoff, cutoff)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def as_of(self, at: str, event_key: str) -> list[dict]:
        cutoff = _timestamp(at)
        rows = self.connection.execute("""
            SELECT * FROM observations
            WHERE event_key = ? AND captured_at <= ? AND observed_at <= ?
            ORDER BY captured_at, observed_at, id
        """, (event_key, cutoff, cutoff)).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload_json"])} for row in rows]

    def scan_gaps(self) -> list[dict]:
        """Return scan receipts with source failures; gaps require comparing scan times."""
        rows = self.connection.execute("SELECT * FROM scan_runs ORDER BY scan_at").fetchall()
        return [{"scan_at": row["scan_at"], "captured_at": row["captured_at"],
                 "source_errors": json.loads(row["manifest_json"]).get("source_errors", []),
                 "data_status": json.loads(row["manifest_json"]).get("data_status")}
                for row in rows]


def archive_snapshot(store: HistoryStore, snapshot: dict, *, captured_at: str,
                     source_url: str, rights_by_provider: dict[str, str]) -> int:
    """Import public snapshot evidence; capture time is the actual import time."""
    manifest = snapshot.get("manifest") or {}
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported snapshot schema")
    scan_at, captured = _timestamp(manifest["last_scan_at"]), _timestamp(captured_at)
    if scan_at > captured:
        raise ValueError("scan cannot postdate capture")
    if not source_url:
        raise ValueError("source URL required")
    records = []
    for incident in snapshot.get("incidents", []):
        if incident.get("kind") != "agency_incident":
            raise ValueError("invalid incident kind")
        provider = incident["provider"]
        records.append({"subject_kind": "agency_incident", "provider": provider,
                        "source_id": incident["official_id"], "record_type": "incident_status",
                        "observed_at": incident.get("modified_at") or incident["last_seen_at"],
                        "captured_at": captured, "source_url": source_url,
                        "rights_url": rights_by_provider[provider], "payload": incident})
    for candidate in snapshot.get("events", []):
        if candidate.get("kind") != "satellite_candidate":
            raise ValueError("invalid candidate kind")
        records.append({"subject_kind": "satellite_candidate", "provider": "firms",
                        "source_id": candidate["event_id"], "record_type": "thermal_observation",
                        "observed_at": candidate["observed_at"], "captured_at": captured,
                        "source_url": source_url, "rights_url": rights_by_provider["firms"],
                        "payload": candidate})
    before = store.connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    try:
        for record in records:
            store.append(record, commit=False)
        added_observations = (store.connection.execute("SELECT COUNT(*) FROM observations")
                              .fetchone()[0] - before)
        raw_manifest = json.dumps(manifest, sort_keys=True, ensure_ascii=False,
                                  separators=(",", ":"), allow_nan=False)
        digest = hashlib.sha256((scan_at + source_url + raw_manifest).encode()).hexdigest()
        store.connection.execute("""
            INSERT OR IGNORE INTO scan_runs
            (id, scan_at, captured_at, source_url, manifest_json) VALUES (?, ?, ?, ?, ?)
        """, (digest, scan_at, captured, source_url, raw_manifest))
        store.connection.commit()
    except Exception:
        store.connection.rollback()
        raise
    return added_observations
