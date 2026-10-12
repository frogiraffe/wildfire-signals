"""Offline import and as-of analysis of published NASA FIRMS pixel research assets.

Consumes existing opt-in GitHub Release assets; performs no source requests,
cloud writes or automatic downloading. Raw VIIRS pixels are NOT confirmed fires.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from .collect import FIRMS_SOURCES
from .history import _timestamp
from .region_diagnostics import distance_km
from .release_archive import MAX_ASSET_BYTES

SCAN_NAME = re.compile(r"firms-pixel-scan-(\d{8}T\d{6}Z)-([a-f0-9]{16})\.json\.gz\Z")
PIXEL_NAME = re.compile(r"firms-pixels-(\d{8}T\d{6}Z)-([a-f0-9]{16})\.jsonl\.gz\Z")
HEX = re.compile(r"[a-f0-9]{64}\Z")
MAX_SCAN_JSON = 1_000_000
MAX_ROW_BYTES = 16_384
MAX_PIXELS_PER_FILE = 250_000
MAX_REPORT_PIXELS = 250_000
MAX_REPORT_SCANS = 10_000


def _read_compressed(path: Path, *, cap: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ASSET_BYTES:
        raise ValueError(f"invalid research asset: {path.name}")
    with gzip.open(path, "rb") as stream:
        data = stream.read(cap + 1)
    if len(data) > cap:
        raise ValueError("decompressed research asset exceeds budget")
    return data


def _stamp(value: str) -> str:
    return datetime.fromisoformat(_timestamp(value)).strftime("%Y%m%dT%H%M%SZ")


def _finite(value, minimum: float, maximum: float) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def _validated_scan(path: Path) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ASSET_BYTES:
        raise ValueError("invalid scan asset")
    match = SCAN_NAME.fullmatch(path.name)
    if not match:
        raise ValueError(f"unexpected scan asset: {path.name}")
    raw_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if raw_digest[:16] != match.group(2):
        raise ValueError("scan asset filename checksum mismatch")
    receipt = json.loads(_read_compressed(path, cap=MAX_SCAN_JSON))
    if receipt.get("schema_version") != 1 or receipt.get("role") != "firms_pixel_scan_receipt":
        raise ValueError("unsupported pixel scan receipt")
    scan_at, captured_at = _timestamp(receipt["scan_at"]), _timestamp(receipt["captured_at"])
    if _stamp(scan_at) != match.group(1) or scan_at > captured_at:
        raise ValueError("pixel receipt scan/capture time mismatch")
    if not isinstance(receipt.get("snapshot_key"), str) or not re.fullmatch(
            r"snapshot:[a-f0-9]{64}", receipt["snapshot_key"]):
        raise ValueError("snapshot key unavailable")
    states = receipt.get("source_states")
    if (not isinstance(states, dict) or set(states) != set(FIRMS_SOURCES)
            or any(value not in {"complete", "failed", "deferred"} for value in states.values())):
        raise ValueError("source states incomplete or invalid")
    files = receipt.get("pixel_files")
    if not isinstance(files, list) or len(files) > len(FIRMS_SOURCES):
        raise ValueError("invalid pixel file manifest")
    names = set()
    for file in files:
        if not isinstance(file, dict) or not isinstance(file.get("name"), str):
            raise ValueError("invalid pixel asset descriptor")
        pixel_match = PIXEL_NAME.fullmatch(file["name"])
        if (not pixel_match or pixel_match.group(1) != match.group(1)
                or not isinstance(file.get("sha256"), str)
                or not HEX.fullmatch(file["sha256"])
                or pixel_match.group(2) != file["sha256"][:16]
                or file["name"] in names):
            raise ValueError("pixel asset name, checksum or stamp mismatch")
        names.add(file["name"])
    return receipt, raw_digest


def _pixel(row: dict, receipt: dict) -> tuple:
    """Validate source-originated raw field digest and UTC/position contract."""
    source = row.get("source")
    if source not in FIRMS_SOURCES or receipt["source_states"][source] != "complete":
        raise ValueError("pixel source inconsistent with completed scan")
    fields = row.get("source_fields")
    if row.get("kind") != "thermal_detection" or not isinstance(fields, dict):
        raise ValueError("not a thermal detection raw record")
    digest = hashlib.sha256(json.dumps(fields, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    if (row.get("content_sha256") != digest
            or row.get("source_record_id") != f"{source}:{digest}"
            or not isinstance(row.get("candidate_id"), str)
            or not row["candidate_id"].startswith("firms-")):
        raise ValueError("thermal pixel provenance mismatch")
    observed, received = _timestamp(row["observed_at"]), _timestamp(row["received_at"])
    if observed > received or received > _timestamp(receipt["captured_at"]):
        raise ValueError("pixel timestamp exceeds confirmed receipt time")
    if not _finite(row.get("latitude"), -90, 90) or not _finite(row.get("longitude"), -180, 180):
        raise ValueError("invalid thermal observation coordinates")
    # A stored digest authenticates the raw fields only relative to the signed
    # receipt asset. Ensure the normalized values were actually derived from it.
    try:
        raw_lat, raw_lon = float(fields["latitude"]), float(fields["longitude"])
        raw_acquired = datetime.strptime(
            f"{fields['acq_date']}{str(fields['acq_time']).zfill(4)}",
            "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc).isoformat()
    except (KeyError, TypeError, ValueError):
        raise ValueError("raw FIRMS coordinates or acquisition time invalid") from None
    if (not math.isfinite(raw_lat) or not math.isfinite(raw_lon)
            or raw_lat != row["latitude"] or raw_lon != row["longitude"]
            or raw_acquired != observed):
        raise ValueError("raw-to-normalized FIRMS fields mismatch")
    frp = row.get("frp_mw")
    if frp is not None and not _finite(frp, 0, 1e9):
        raise ValueError("invalid FRP")
    for field in ("source_url", "rights_url"):
        if (not isinstance(row.get(field), str) or
                not row[field].startswith("https://")):
            raise ValueError("missing upstream source/rights provenance")
    return (row["source_record_id"], digest, source, row["candidate_id"], observed,
            _timestamp(receipt["captured_at"]), _timestamp(receipt["scan_at"]),
            received, float(row["latitude"]), float(row["longitude"]), frp,
            row["source_url"], row["rights_url"])


def _create_tables(db: sqlite3.Connection) -> None:
    db.executescript("""
        CREATE TABLE IF NOT EXISTS pixel_scans (
            scan_at TEXT PRIMARY KEY,
            captured_at TEXT NOT NULL,
            snapshot_key TEXT NOT NULL,
            receipt_sha256 TEXT NOT NULL,
            source_states_json TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pixel_scan_assets (
            scan_at TEXT NOT NULL,
            asset_name TEXT NOT NULL,
            asset_sha256 TEXT NOT NULL,
            rows_seen INTEGER NOT NULL,
            PRIMARY KEY (scan_at, asset_name)
        );
        CREATE TABLE IF NOT EXISTS pixel_observations (
            source_record_id TEXT PRIMARY KEY,
            raw_sha256 TEXT NOT NULL,
            provider TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            first_captured_at TEXT NOT NULL,
            first_scan_at TEXT NOT NULL,
            source_received_at TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            frp_mw REAL,
            source_url TEXT NOT NULL,
            rights_url TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS pixel_observed_at ON pixel_observations(observed_at);
        CREATE INDEX IF NOT EXISTS pixel_received_at ON pixel_observations(first_captured_at);
    """)


def import_release_assets(db_path: str | Path, directory: str | Path) -> dict:
    """Transactionally import all local daily release asset sets, without network.

    Every scan receipt requires precisely its declared pixel assets. An
    interrupted/conflicting batch rolls back; repeated identical scans skip.
    """
    directory = Path(directory)
    scans = sorted(directory.rglob("firms-pixel-scan-*.json.gz"))
    if not scans:
        raise ValueError("no pixel scan receipts found")
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path)
    imported = files_read = rows_read = rows_inserted = duplicates = 0
    try:
        _create_tables(db)
        db.commit()
        db.execute("BEGIN")
        seen_scans = set()
        for path in scans:
            receipt, digest = _validated_scan(path)
            scan_at, captured_at = _timestamp(receipt["scan_at"]), _timestamp(receipt["captured_at"])
            if scan_at in seen_scans:
                raise ValueError("duplicate scan time in input batch")
            seen_scans.add(scan_at)
            existing = db.execute("""
                SELECT captured_at,snapshot_key,receipt_sha256,source_states_json
                FROM pixel_scans WHERE scan_at=?
            """, (scan_at,)).fetchone()
            states_json = json.dumps(receipt["source_states"], sort_keys=True,
                                     separators=(",", ":"))
            provenance = (captured_at,receipt["snapshot_key"],digest,states_json)
            if existing is not None:
                if tuple(existing) != provenance:
                    raise ValueError("conflicting historical pixel scan")
                continue
            declared = {entry["name"]: entry["sha256"] for entry in receipt["pixel_files"]}
            present = {p.name for p in path.parent.glob(f"firms-pixels-{_stamp(scan_at)}-*.jsonl.gz")}
            if present != set(declared):
                raise ValueError("missing or unexpected pixel files for scan")
            db.execute("""INSERT INTO pixel_scans
                (scan_at,captured_at,snapshot_key,receipt_sha256,source_states_json)
                VALUES (?,?,?,?,?)""", (scan_at,*provenance))
            imported += 1
            for name,expected_digest in sorted(declared.items()):
                file = path.parent/name
                if (file.is_symlink() or not file.is_file()
                        or file.stat().st_size > MAX_ASSET_BYTES
                        or hashlib.sha256(file.read_bytes()).hexdigest() != expected_digest):
                    raise ValueError("pixel asset checksum or size mismatch")
                files_read += 1
                count = 0
                with gzip.open(file,"rb") as source:
                    while True:
                        line = source.readline(MAX_ROW_BYTES + 1)
                        if not line:
                            break
                        if len(line) > MAX_ROW_BYTES or not line.endswith(b"\n"):
                            raise ValueError("pixel JSONL record size/terminator invalid")
                        if count >= MAX_PIXELS_PER_FILE:
                            raise ValueError("pixel source row budget exceeded")
                        row = json.loads(line)
                        values = _pixel(row,receipt)
                        rows_read += 1
                        count += 1
                        cursor = db.execute("""INSERT OR IGNORE INTO pixel_observations
                            (source_record_id,raw_sha256,provider,candidate_id,observed_at,
                             first_captured_at,first_scan_at,source_received_at,
                             latitude,longitude,frp_mw,source_url,rights_url)
                            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",values)
                        if cursor.rowcount:
                            rows_inserted += 1
                        else:
                            duplicates += 1
                db.execute("""INSERT INTO pixel_scan_assets
                    (scan_at,asset_name,asset_sha256,rows_seen) VALUES (?,?,?,?)""",
                    (scan_at,name,expected_digest,count))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return {"schema_version":1,"imported_scans":imported,"pixel_assets_processed":files_read,
            "pixel_rows_read":rows_read,"new_unique_pixels":rows_inserted,
            "duplicate_observations":duplicates,
            "role":"archived satellite thermal detections, NOT confirmed fires"}


def coverage_report(db_path: str | Path, *, at: str, hours: int = 72,
                    latitude: float | None = None, longitude: float | None = None,
                    radius_km: float | None = None) -> dict:
    """Summarize coverage and pixels independently; missing scans are unknown."""
    if type(hours) is not int or not 1 <= hours <= 168:
        raise ValueError("hours must be 1..168")
    region = any(x is not None for x in (latitude,longitude,radius_km))
    if region:
        if (not all(x is not None for x in (latitude,longitude,radius_km))
                or not _finite(latitude,-90,90) or not _finite(longitude,-180,180)
                or not _finite(radius_km,0.001,20000)):
            raise ValueError("invalid worldwide search circle")
    cutoff = _timestamp(at)
    start = (datetime.fromisoformat(cutoff) - timedelta(hours=hours)).isoformat()
    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(path)
    uri = "file:" + quote(str(path.resolve()),safe="/") + "?mode=ro"
    with closing(sqlite3.connect(uri,uri=True)) as db:
        db.row_factory = sqlite3.Row
        scans = db.execute("""SELECT scan_at,captured_at,source_states_json
            FROM pixel_scans WHERE scan_at BETWEEN ? AND ? AND captured_at<=?
            ORDER BY scan_at ASC LIMIT ?""",
            (start,cutoff,cutoff,MAX_REPORT_SCANS+1)).fetchall()
        scans_truncated = len(scans)>MAX_REPORT_SCANS
        scans = scans[:MAX_REPORT_SCANS]
        pixels = db.execute("""SELECT source_record_id,provider,observed_at,latitude,longitude
            FROM pixel_observations
            WHERE observed_at BETWEEN ? AND ? AND first_captured_at<=?
            ORDER BY observed_at ASC LIMIT ?""",
            (start,cutoff,cutoff,MAX_REPORT_PIXELS+1)).fetchall()
        pixels_truncated = len(pixels)>MAX_REPORT_PIXELS
        pixels = pixels[:MAX_REPORT_PIXELS]
    states = Counter()
    latest = {source:{"status":"no_scan_available","scan_at":None} for source in FIRMS_SOURCES}
    gaps = []
    for index,scan in enumerate(scans):
        current = json.loads(scan["source_states_json"])
        for source,state in current.items():
            states[f"{source}:{state}"] += 1
            latest[source] = {"status":state,"scan_at":scan["scan_at"]}
        if index:
            gap = (datetime.fromisoformat(scan["scan_at"]) -
                   datetime.fromisoformat(scans[index-1]["scan_at"])).total_seconds()/3600
            if gap>9:
                gaps.append({"from":scans[index-1]["scan_at"],"to":scan["scan_at"],
                             "hours":round(gap,3)})
    by_sensor = Counter()
    cell_hours = set()
    cells = defaultdict(set)
    missing_region = 0
    for pixel in pixels:
        if region and distance_km(latitude,longitude,pixel["latitude"],pixel["longitude"])>radius_km:
            missing_region+=1
            continue
        by_sensor[pixel["provider"]]+=1
        hour = datetime.fromisoformat(pixel["observed_at"]).replace(
            minute=0,second=0,microsecond=0).isoformat()
        # Match the public map's 0.05-degree spatial bucket and UTC hour.
        # This is a candidate aggregation, not a physical wildfire boundary.
        cell = (math.floor(pixel["latitude"] * 20),
                math.floor(pixel["longitude"] * 20))
        cells[cell].add(hour)
        cell_hours.add((cell,hour))
    return {"schema_version":1,"decision_at":cutoff,"window_hours":hours,
        "geographic_scope":({"type":"circle","latitude":latitude,"longitude":longitude,
                             "radius_km":radius_km} if region else {"type":"all_archived_pixels"}),
        "completed_scan_receipts":len(scans),"scan_query_truncated":scans_truncated,
        "pixel_query_truncated":pixels_truncated,"source_state_counts":dict(sorted(states.items())),
        "latest_source_state":latest,"receipt_gaps_over_9_hours":gaps,
        "unique_raw_pixel_observations":sum(by_sensor.values()),
        "aggregation":"0.05 degree spatial cell by UTC hour",
        "candidate_cell_hours":len(cell_hours),"distinct_observed_cells":len(cells),
        "cells_observed_multiple_hours":sum(len(h)>1 for h in cells.values()),
        "pixel_counts_by_sensor":dict(sorted(by_sensor.items())),
        "pixels_outside_region":missing_region,
        "evidence_completeness":"unverified",
        "fire_confirmation":False,
        "warning":"An archived FIRMS thermal detection is not an independently verified wildfire. "
                  "A missing receipt, source failure or zero observations never proves absence of fire."}


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline FIRMS research release importer/coverage report")
    commands = parser.add_subparsers(dest="action",required=True)
    ingest = commands.add_parser("import",help="Verify downloaded research release assets and import")
    ingest.add_argument("--db",required=True,type=Path)
    ingest.add_argument("--assets",required=True,type=Path)
    report = commands.add_parser("report",help="Read-only historical regional coverage report")
    report.add_argument("--db",required=True,type=Path)
    report.add_argument("--at",required=True)
    report.add_argument("--hours",type=int,default=72)
    report.add_argument("--latitude",type=float)
    report.add_argument("--longitude",type=float)
    report.add_argument("--radius-km",type=float)
    report.add_argument("--output",type=Path)
    args = parser.parse_args()
    if args.action=="import":
        result=import_release_assets(args.db,args.assets)
    else:
        result=coverage_report(args.db,at=args.at,hours=args.hours,
                               latitude=args.latitude,longitude=args.longitude,
                               radius_km=args.radius_km)
        if args.output:
            if args.output.exists() or args.output.resolve()==args.db.resolve():
                parser.error("report refuses to overwrite existing files or source database")
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
