"""Bounded-memory SQLite rollup benchmark on clearly synthetic scale fixtures.

Fixture rows are never scientific observations. Output stays outside Git.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import resource
import sqlite3
import time

from fire_public.collect import FIRMS_SOURCES
from fire_public.historical_rollup import build_rollup, query_rollup
from fire_public.pixel_history import _create_tables


def benchmark(path: Path, rows: int) -> dict:
    if rows <= 1_000_000 or path.exists() or path.is_symlink():
        raise ValueError("benchmark requires >1,000,000 rows and a new path")
    db = sqlite3.connect(path)
    _create_tables(db)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    insert = """INSERT INTO pixel_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    started = time.monotonic()
    for scan_no in range(5):
        scan_at = (base + timedelta(hours=6 * scan_no)).isoformat()
        db.execute("INSERT INTO pixel_scans VALUES(?,?,?,?,?)",
                   (scan_at, scan_at, "synthetic:benchmark", "a" * 64,
                    json.dumps({source: "complete" for source in FIRMS_SOURCES})))
        db.execute("INSERT INTO pixel_scan_assets VALUES(?,?,?,?)",
                   (scan_at, f"synthetic-asset-{scan_no}", "b" * 64, 0))
        begin, end = rows * scan_no // 5, rows * (scan_no + 1) // 5
        for offset in range(begin, end, 10_000):
            batch = []
            for i in range(offset, min(end, offset + 10_000)):
                inside = i % 100 == 0
                observed = (base + timedelta(hours=6 * scan_no - 1,
                                              minutes=i % 60)).isoformat()
                batch.append((f"synthetic:{i}", "c" * 64, FIRMS_SOURCES[i % 2],
                     f"synthetic-{i}", observed, scan_at, scan_at, scan_at,
                     37.93 if inside else 70.0, 41.12 if inside else 0.0, None,
                     "https://example.invalid/synthetic", "https://example.invalid/synthetic"))
            db.executemany(insert, batch)
            db.commit()
    generation_s = round(time.monotonic() - started, 3)
    db.close()
    region = [{"region_id": "BENCHMARK", "latitude": 37.929, "longitude": 41.1166,
               "radius_km": 25}]
    started = time.monotonic()
    first = build_rollup(path, region, max_scans=2)
    first_s = round(time.monotonic() - started, 3)
    started = time.monotonic()
    resumed = build_rollup(path, region)
    resume_s = round(time.monotonic() - started, 3)
    started = time.monotonic()
    repeated = build_rollup(path, region)
    repeated_s = round(time.monotonic() - started, 3)
    started = time.monotonic()
    query = query_rollup(path, region, start_date="2025-12-31", end_date="2026-01-02")
    query_s = round(time.monotonic() - started, 3)
    if (first["processed_scans"] != 2 or resumed["processed_scans"] != 5 or
        repeated["newly_processed_scans"] != 0 or
        query["population"]["selected_raw_pixels"] != (rows + 99) // 100):
        raise AssertionError("synthetic benchmark count/checkpoint mismatch")
    return {"fixture_only_not_observations": True, "synthetic_rows": rows,
            "generation_s": generation_s, "first_two_scans_s": first_s,
            "remaining_three_scans_s": resume_s, "idempotent_recheck_s": repeated_s,
            "date_query_s": query_s, "database_bytes": path.stat().st_size,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "selected_raw_pixels": query["population"]["selected_raw_pixels"],
            "distinct_candidate_cell_hours": query["population"]["distinct_candidate_cell_hours"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=1_000_001)
    args = parser.parse_args()
    print(json.dumps(benchmark(args.db, args.rows), sort_keys=True))
