"""Checkpointed thermal candidate rollups inside the existing pixel SQLite DB.

Raw records remain source-of-truth. A study is queryable only after all known scans
have been processed. No zero-filled non-detections or satellite exposure claims.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import sqlite3

from .collect import FIRMS_SOURCES
from .historical_signal_analysis import _read_only, _utc
from .observational_cohort import validate_regions
from .observation_opportunity import STATES, classify_interval
from .region_diagnostics import distance_km

SCHEMA_VERSION = 1
MAX_QUERY_DAYS = 366


def _bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def _study(regions: list[dict]) -> tuple[str, list[dict], str]:
    chosen = validate_regions(regions)
    contract = {"version": SCHEMA_VERSION, "aggregation": "0.05_degree_utc_hour_v1",
                "regions": chosen}
    body = _bytes(contract).decode().strip()
    return hashlib.sha256(body.encode()).hexdigest()[:20], chosen, body


def _schema(db: sqlite3.Connection) -> None:
    db.executescript("""
      CREATE TABLE IF NOT EXISTS analytics_schema_meta(version INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS analytics_studies(
        study_id TEXT PRIMARY KEY, contract_json TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('building','ready')));
      CREATE TABLE IF NOT EXISTS analytics_processed_scans(
        study_id TEXT NOT NULL, scan_at TEXT NOT NULL, receipt_sha256 TEXT NOT NULL,
        asset_manifest_sha256 TEXT NOT NULL, captured_at TEXT NOT NULL,
        source_states_json TEXT NOT NULL, raw_pixels INTEGER NOT NULL,
        selected_raw_pixels INTEGER NOT NULL, new_candidate_cell_hours INTEGER NOT NULL,
        PRIMARY KEY(study_id,scan_at));
      CREATE TABLE IF NOT EXISTS analytics_region_pixels(
        study_id TEXT NOT NULL, source_record_id TEXT NOT NULL, region_id TEXT NOT NULL,
        provider TEXT NOT NULL, observed_at TEXT NOT NULL, first_captured_at TEXT NOT NULL,
        first_scan_at TEXT NOT NULL, observed_hour TEXT NOT NULL,
        lat_cell INTEGER NOT NULL, lon_cell INTEGER NOT NULL,
        PRIMARY KEY(study_id,source_record_id));
      CREATE INDEX IF NOT EXISTS analytics_raw_region_time
        ON analytics_region_pixels(study_id,region_id,observed_at);
      CREATE TABLE IF NOT EXISTS analytics_cell_hours(
        study_id TEXT NOT NULL, region_id TEXT NOT NULL, lat_cell INTEGER NOT NULL,
        lon_cell INTEGER NOT NULL, observed_hour TEXT NOT NULL,
        first_captured_at TEXT NOT NULL, first_scan_at TEXT NOT NULL,
        PRIMARY KEY(study_id,region_id,lat_cell,lon_cell,observed_hour));
      CREATE INDEX IF NOT EXISTS analytics_cells_region_hour
        ON analytics_cell_hours(study_id,region_id,observed_hour);
      CREATE INDEX IF NOT EXISTS pixel_first_scan_for_analytics
        ON pixel_observations(first_scan_at);
    """)
    rows = db.execute("SELECT version FROM analytics_schema_meta").fetchall()
    if not rows:
        db.execute("INSERT INTO analytics_schema_meta VALUES(?)", (SCHEMA_VERSION,))
        db.commit()
    elif len(rows) != 1 or rows[0][0] != SCHEMA_VERSION:
        raise ValueError("unsupported analytics schema version; explicit migration required")


def _asset_digest(db: sqlite3.Connection, scan_at: str) -> str:
    rows = [dict(row) for row in db.execute("""SELECT asset_name,asset_sha256,rows_seen
         FROM pixel_scan_assets WHERE scan_at=? ORDER BY asset_name""", (scan_at,))]
    return hashlib.sha256(_bytes(rows)).hexdigest()


def build_rollup(pixel_db: str | Path, regions: list[dict], *,
                 max_scans: int | None = None, rebuild: bool = False,
                 batch_size: int = 2000) -> dict:
    """Process one receipt per SQLite transaction; resume after interruption."""
    if max_scans is not None and (type(max_scans) is not int or max_scans < 1):
        raise ValueError("max_scans must be positive")
    if type(batch_size) is not int or not 100 <= batch_size <= 10_000:
        raise ValueError("batch_size must be between 100 and 10000")
    path = Path(pixel_db)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    study_id, chosen, contract = _study(regions)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        _schema(db)
        scans = db.execute("""SELECT scan_at,captured_at,receipt_sha256,source_states_json
                              FROM pixel_scans ORDER BY scan_at""").fetchall()
        if not scans:
            raise ValueError("no verified pixel scan receipts")
        existing = db.execute("SELECT contract_json FROM analytics_studies WHERE study_id=?",
                              (study_id,)).fetchone()
        if existing and existing[0] != contract:
            raise ValueError("study hash collision or changed region contract")
        if rebuild:
            with db:
                for table in ("analytics_region_pixels", "analytics_cell_hours",
                              "analytics_processed_scans"):
                    db.execute(f"DELETE FROM {table} WHERE study_id=?", (study_id,))
                db.execute("""INSERT INTO analytics_studies VALUES(?,?,'building')
                    ON CONFLICT(study_id) DO UPDATE SET state='building'""", (study_id,contract))
        elif not existing:
            with db:
                db.execute("INSERT INTO analytics_studies VALUES(?,?,'building')",(study_id,contract))
        processed = db.execute("""SELECT scan_at,receipt_sha256,asset_manifest_sha256,raw_pixels
             FROM analytics_processed_scans WHERE study_id=? ORDER BY scan_at""", (study_id,)).fetchall()
        if [row["scan_at"] for row in processed] != [row["scan_at"] for row in scans[:len(processed)]]:
            raise ValueError("new earlier scan or altered history requires explicit rebuild")
        for old, scan in zip(processed, scans):
            count = db.execute("SELECT COUNT(*) FROM pixel_observations WHERE first_scan_at=?",
                               (scan["scan_at"],)).fetchone()[0]
            if (old["receipt_sha256"] != scan["receipt_sha256"] or
                old["asset_manifest_sha256"] != _asset_digest(db,scan["scan_at"]) or
                old["raw_pixels"] != count):
                raise ValueError("source evidence or first-capture history changed; rebuild required")
        remaining = scans[len(processed):]
        if remaining:
            with db:
                db.execute("UPDATE analytics_studies SET state='building' WHERE study_id=?",(study_id,))
        selected_scans = remaining[:max_scans] if max_scans is not None else remaining
        for scan in selected_scans:
            scan_at = scan["scan_at"]
            raw_count = selected_count = new_cells = 0
            db.execute("BEGIN IMMEDIATE")
            try:
                source = db.execute("""SELECT source_record_id,provider,observed_at,
                    first_captured_at,first_scan_at,latitude,longitude
                    FROM pixel_observations WHERE first_scan_at=? ORDER BY source_record_id""",
                    (scan_at,))
                while rows := source.fetchmany(batch_size):
                    for pixel in rows:
                        raw_count += 1
                        observed, captured = _utc(pixel["observed_at"]), _utc(pixel["first_captured_at"])
                        if (pixel["provider"] not in FIRMS_SOURCES or
                            pixel["first_scan_at"] != scan_at or
                            not observed <= captured <= _utc(scan["captured_at"])):
                            raise ValueError("invalid source or temporal provenance")
                        lat, lon = pixel["latitude"],pixel["longitude"]
                        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                            raise ValueError("pixel outside WGS84 range")
                        region = next((r for r in chosen if distance_km(lat,lon,r["latitude"],
                                       r["longitude"]) <= r["radius_km"]), None)
                        if region is None:
                            continue
                        selected_count += 1
                        hour = observed.replace(minute=0,second=0,microsecond=0).isoformat()
                        lat_cell = math.floor(lat * 20)
                        lon_cell = math.floor(((lon + 180) % 360 - 180) * 20)
                        db.execute("""INSERT INTO analytics_region_pixels VALUES(?,?,?,?,?,?,?,?,?,?)""",
                            (study_id,pixel["source_record_id"],region["region_id"],pixel["provider"],
                             observed.isoformat(),captured.isoformat(),scan_at,hour,lat_cell,lon_cell))
                        inserted = db.execute("""INSERT OR IGNORE INTO analytics_cell_hours
                            VALUES(?,?,?,?,?,?,?)""",
                            (study_id,region["region_id"],lat_cell,lon_cell,hour,
                             captured.isoformat(),scan_at))
                        new_cells += inserted.rowcount
                db.execute("""INSERT INTO analytics_processed_scans VALUES(?,?,?,?,?,?,?,?,?)""",
                    (study_id,scan_at,scan["receipt_sha256"],_asset_digest(db,scan_at),
                     scan["captured_at"],scan["source_states_json"],raw_count,
                     selected_count,new_cells))
                db.commit()
            except Exception:
                db.rollback()
                raise
        total_processed = len(processed) + len(selected_scans)
        if total_processed == len(scans):
            with db:
                db.execute("UPDATE analytics_studies SET state='ready' WHERE study_id=?",(study_id,))
        return {"schema_version":SCHEMA_VERSION,"study_id":study_id,
                "state":"ready" if total_processed==len(scans) else "building",
                "newly_processed_scans":len(selected_scans),
                "processed_scans":total_processed,"known_scans":len(scans),
                "bounded_batch_size":batch_size}
    finally:
        db.close()


def query_rollup(pixel_db: str | Path, regions: list[dict], *,
                 start_date: str, end_date: str, resolution: str = "day",
                 region_ids: list[str] | None = None) -> dict:
    """Read a bounded date range; absent rows are unknown, not zero fire activity."""
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end-start).days >= MAX_QUERY_DAYS:
        raise ValueError("query must cover 1..366 UTC dates")
    if resolution not in ("day","hour"):
        raise ValueError("unsupported resolution")
    study_id, chosen, contract = _study(regions)
    ids = sorted(set(region_ids or [r["region_id"] for r in chosen]))
    if not ids or len(ids) != len(region_ids or ids) or not set(ids) <= {r["region_id"] for r in chosen}:
        raise ValueError("invalid selected region IDs")
    lower = start.isoformat() + "T"
    upper = (end+timedelta(days=1)).isoformat() + "T"
    bucket = "substr(observed_at,1,10)" if resolution=="day" else "substr(observed_at,1,13)"
    cell_bucket = "substr(observed_hour,1,10)" if resolution=="day" else "substr(observed_hour,1,13)"
    placeholders = ",".join("?" for _ in ids)
    with closing(_read_only(Path(pixel_db))) as db:
        study = db.execute("SELECT contract_json,state FROM analytics_studies WHERE study_id=?",
                           (study_id,)).fetchone()
        if not study or study["contract_json"]!=contract or study["state"]!="ready":
            raise ValueError("analytics study is missing or building")
        raw = db.execute(f"""SELECT region_id,{bucket} AS period,COUNT(*) AS n,
            MIN(observed_at) AS first_observed_at,MAX(observed_at) AS last_observed_at,
            MIN(first_captured_at) AS first_captured_at,MAX(first_captured_at) AS last_captured_at
            FROM analytics_region_pixels WHERE study_id=? AND region_id IN ({placeholders})
            AND observed_at>=? AND observed_at<? GROUP BY region_id,period""",
            (study_id,*ids,lower,upper)).fetchall()
        cells = db.execute(f"""SELECT region_id,{cell_bucket} AS period,COUNT(*) AS n
            FROM analytics_cell_hours WHERE study_id=? AND region_id IN ({placeholders})
            AND observed_hour>=? AND observed_hour<? GROUP BY region_id,period""",
            (study_id,*ids,lower,upper)).fetchall()
        providers = db.execute(f"""SELECT provider,COUNT(*) AS n FROM analytics_region_pixels
            WHERE study_id=? AND region_id IN ({placeholders}) AND observed_at>=? AND observed_at<?
            GROUP BY provider ORDER BY provider""",(study_id,*ids,lower,upper)).fetchall()
        # Include scans around the observed window to show original collection and delay.
        receipt_lower=(start-timedelta(days=4)).isoformat()+"T"
        receipt_upper=(end+timedelta(days=5)).isoformat()+"T"
        receipts=[dict(row) for row in db.execute("""SELECT scan_at,captured_at,receipt_sha256,
                 asset_manifest_sha256,source_states_json,raw_pixels,selected_raw_pixels,
                 new_candidate_cell_hours FROM analytics_processed_scans
                 WHERE study_id=? AND scan_at>=? AND scan_at<? ORDER BY scan_at""",
                 (study_id,receipt_lower,receipt_upper))]
        asset_manifest=[dict(row) for row in db.execute("""SELECT a.scan_at,a.asset_name,
                 a.asset_sha256,a.rows_seen FROM pixel_scan_assets AS a
                 JOIN analytics_processed_scans AS s ON s.scan_at=a.scan_at
                 WHERE s.study_id=? AND a.scan_at>=? AND a.scan_at<?
                 ORDER BY a.scan_at,a.asset_name""",
                 (study_id,receipt_lower,receipt_upper))]
        source_provenance=[dict(row) for row in db.execute(f"""SELECT DISTINCT
                 p.provider,p.source_url,p.rights_url FROM analytics_region_pixels AS r
                 JOIN pixel_observations AS p ON p.source_record_id=r.source_record_id
                 WHERE r.study_id=? AND r.region_id IN ({placeholders})
                 AND r.observed_at>=? AND r.observed_at<?
                 ORDER BY p.provider,p.source_url,p.rights_url""",
                 (study_id,*ids,lower,upper))]
    raw_lookup = {(row["region_id"],row["period"]): row for row in raw}
    cell_lookup = {(row["region_id"],row["period"]):row["n"] for row in cells}
    keys = sorted(raw_lookup.keys() | cell_lookup.keys())
    output_rows = []
    for region_id,period in keys:
        row=raw_lookup.get((region_id,period))
        output_rows.append({"region_id":region_id,"period":period,
            "new_raw_pixels":row["n"] if row else 0,
            "new_candidate_cell_hours":cell_lookup.get((region_id,period),0),
            "first_observed_at":row["first_observed_at"] if row else None,
            "last_observed_at":row["last_observed_at"] if row else None,
            "first_captured_at":row["first_captured_at"] if row else None,
            "last_captured_at":row["last_captured_at"] if row else None,
            "archive_period_complete":False,
            "observation_state":classify_interval(archived_candidates=cell_lookup.get((region_id,period),0),
                                                   retrieval=None),
            "satellite_observation_opportunity":"unknown"})
    for receipt in receipts:
        receipt["source_states"] = json.loads(receipt.pop("source_states_json"))
    report={"schema_version":SCHEMA_VERSION,"study_id":study_id,"regions":chosen,
        "selected_region_ids":ids,"start_date":start.isoformat(),"end_date":end.isoformat(),
        "resolution":resolution,
        ("daily_rows" if resolution=="day" else "hourly_rows"):output_rows,
        "population":{"selected_raw_pixels":sum(row["new_raw_pixels"] for row in output_rows),
                      "distinct_candidate_cell_hours":sum(row["new_candidate_cell_hours"] for row in output_rows)},
        "provider_raw_pixels":{row["provider"]:row["n"] for row in providers},
        "source_receipts":receipts,"source_asset_manifest":asset_manifest,
        "source_provenance":source_provenance,"satellite_opportunity_verified":False,
        "observation_state_schema_version":1,"observation_state_contract":STATES,
        "verified_fire_count":None,
        "warning":"Counts are first archived FIRMS thermal candidates. Missing days and zero new archives do not prove no fire or satellite acquisition."}
    report["evidence_sha256"] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixel-db",required=True,type=Path)
    parser.add_argument("--regions-json",required=True,type=Path)
    parser.add_argument("--max-scans",type=int)
    parser.add_argument("--rebuild",action="store_true")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--resolution",choices=("day","hour"),default="day")
    parser.add_argument("--output-json",type=Path)
    args=parser.parse_args()
    regions=json.loads(args.regions_json.read_text())
    result=build_rollup(args.pixel_db,regions,max_scans=args.max_scans,rebuild=args.rebuild)
    print(json.dumps(result,sort_keys=True))
    if args.output_json:
        if not args.start_date or not args.end_date or args.output_json.exists() or args.output_json.is_symlink():
            parser.error("output requires date bounds and a new file")
        report=query_rollup(args.pixel_db,regions,start_date=args.start_date,
                            end_date=args.end_date,resolution=args.resolution)
        args.output_json.write_bytes(_bytes(report))


if __name__ == "__main__":
    main()
