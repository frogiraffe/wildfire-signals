"""Bounded, offline analysis of originally archived FIRMS thermal candidates.

The experimental model predicts the next *collection output*, never fire occurrence.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .collect import FIRMS_SOURCES
from .historical_signal_analysis import _read_only, _utc
from .observational_cohort import validate_regions
from .region_diagnostics import distance_km

MAX_SCANS = 64
MAX_PIXELS = 1_000_000
MAX_REPORT_BYTES = 1_000_000


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def _period_rows(daily: list[dict], period: str) -> list[dict]:
    grouped = defaultdict(list)
    for row in daily:
        day = datetime.fromisoformat(row["observed_date"])
        key = (day.strftime("%G-W%V") if period == "week" else day.strftime("%Y-%m"))
        grouped[(row["region_id"], key)].append(row)
    return [{"region_id": region, "period": key,
             "new_raw_pixels": sum(r["new_raw_pixels"] for r in rows),
             "new_candidate_cell_hours": sum(r["new_candidate_cell_hours"] for r in rows),
             "archive_period_complete": False}
            for (region, key), rows in sorted(grouped.items())]


def _rolling_rows(daily: list[dict]) -> None:
    by_region = defaultdict(list)
    for row in daily:
        by_region[row["region_id"]].append(row)
    for rows in by_region.values():
        rows.sort(key=lambda row: row["observed_date"])
        for i, row in enumerate(rows):
            prior = rows[max(0, i - 2):i + 1]
            dates = [datetime.fromisoformat(item["observed_date"]).date() for item in prior]
            contiguous = len(dates) == 3 and (dates[-1] - dates[0]).days == 2
            row["rolling_3_observed_days"] = (round(sum(item["new_candidate_cell_hours"]
                 for item in prior) / 3, 6) if contiguous else None)


def _metrics(pairs: list[tuple[int, int, float]]) -> dict:
    n = len(pairs)
    result = {"n": n}
    for name, index in (("persistence", 1), ("log_linear", 2)):
        errors = [pair[index] - pair[0] for pair in pairs]
        result[f"{name}_mae"] = round(sum(abs(e) for e in errors) / n, 6) if n else None
        result[f"{name}_rmse"] = round(math.sqrt(sum(e * e for e in errors) / n), 6) if n else None
        result[f"{name}_bias"] = round(sum(errors) / n, 6) if n else None
    return result


def evaluate_capture_model(scan_rows: list[dict], scans: list[dict],
                           heldout_region_ids: list[str]) -> dict:
    """Fit only on past scan transitions and disjoint regions; no fire labels."""
    base = {"target": "next_scan_new_candidate_cell_hours",
            "observation_unit": "region_by_next_archival_scan",
            "wildfire_prediction_skill": None}
    if len(scans) < 5:
        return dict(base, status="withheld", reason="at least 5 scans required")
    if any(any(scan["source_states"].get(source) != "complete"
                   for source in FIRMS_SOURCES) for scan in scans):
        return dict(base, status="withheld", reason="all sources must have complete scan receipts")
    gaps = [(_utc(scans[i + 1]["scan_at"]) - _utc(scans[i]["scan_at"])).total_seconds() / 3600
            for i in range(len(scans) - 1)]
    if any(not 5 <= gap <= 7 for gap in gaps):
        return dict(base, status="withheld", reason="regular six-hour receipt cadence required")
    lookup = {(row["scan_index"], row["region_id"]): row["new_candidate_cell_hours"]
              for row in scan_rows}
    regions = sorted({row["region_id"] for row in scan_rows})
    if len(lookup) != len(scan_rows) or len(lookup) != len(scans) * len(regions):
        raise ValueError("incomplete or duplicate scan/region observations")
    heldout = set(heldout_region_ids)
    if not heldout or not heldout < set(regions):
        raise ValueError("holdout must be a nonempty proper subset of regions")
    samples = []
    # The first transition includes the initial 72-hour bootstrap and is incomparable.
    for scan_index in range(1, len(scans) - 1):
        for region in regions:
            x, y = lookup[(scan_index, region)], lookup[(scan_index + 1, region)]
            if type(x) is not int or type(y) is not int or min(x, y) < 0:
                raise ValueError("candidate counts must be nonnegative integers")
            samples.append((scan_index, region, x, y))
    last_feature_index = len(scans) - 2
    train = [s for s in samples if s[0] < last_feature_index and s[1] not in heldout]
    if len(train) < 8:
        return dict(base, status="withheld", reason="at least eight earlier regional transitions required")
    xs = [math.log1p(s[2]) for s in train]
    ys = [math.log1p(s[3]) for s in train]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    variance = sum((x - mx) ** 2 for x in xs)
    slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / variance
             if variance > 1e-12 else 0.0)
    intercept = my - slope * mx

    def score(group):
        pairs = []
        for _, _, current, target in group:
            fitted = max(0.0, math.expm1(min(20.0, intercept + slope * math.log1p(current))))
            pairs.append((target, current, fitted))
        return _metrics(pairs)

    split = {
        "train": train,
        "temporal_holdout": [s for s in samples if s[0] == last_feature_index and s[1] not in heldout],
        "geographic_holdout": [s for s in samples if s[0] < last_feature_index and s[1] in heldout],
        "joint_holdout": [s for s in samples if s[0] == last_feature_index and s[1] in heldout],
    }
    degenerate = len({s[3] for s in train}) < 2 or variance <= 1e-12
    return dict(base, status="experimental", feature="current_scan_new_candidate_cell_hours",
                model="ordinary_least_squares_log1p_single_lag",
                baseline="persistence_of_current_scan_count",
                degenerate_training_target=degenerate,
                model_comparison_supported=not degenerate,
                coefficients={"intercept": round(intercept, 9), "slope": round(slope, 9)},
                training_last_target_scan_at=scans[-2]["scan_at"],
                first_temporal_holdout_target_scan_at=scans[-1]["scan_at"],
                splits={key: score(group) for key, group in split.items()},
                limitation="Small opportunistic archive; tests concern collection output, not fires. "
                           "No independent satellite opportunity or fire labels; no skill claim.")


def build_capture_pilot(db_path: str | Path, regions: list[dict], *,
                        heldout_region_ids: list[str]) -> dict:
    """Aggregate a verified SQLite pixel archive to deterministic region/scan rows."""
    chosen = validate_regions(regions)
    heldout = sorted(set(heldout_region_ids))
    if len(heldout) != len(heldout_region_ids) or not set(heldout) < {r["region_id"] for r in chosen}:
        raise ValueError("holdout must be a nonempty proper subset of distinct regions")
    with closing(_read_only(Path(db_path))) as db:
        raw_scans = db.execute("""SELECT scan_at,captured_at,snapshot_key,receipt_sha256,
                                      source_states_json FROM pixel_scans ORDER BY scan_at""").fetchall()
        if not 1 <= len(raw_scans) <= MAX_SCANS:
            raise ValueError("scan count outside bounded pilot range")
        scans = []
        for scan in raw_scans:
            states = json.loads(scan["source_states_json"])
            if set(states) != set(FIRMS_SOURCES) or any(state not in
                    {"complete", "failed", "deferred"} for state in states.values()):
                raise ValueError("unsupported source receipt state")
            scans.append({"scan_at": scan["scan_at"], "captured_at": scan["captured_at"],
                          "snapshot_key": scan["snapshot_key"],
                          "receipt_sha256": scan["receipt_sha256"],
                          "source_states": states})
        count = db.execute("SELECT COUNT(*) FROM pixel_observations").fetchone()[0]
        if count > MAX_PIXELS:
            raise ValueError("pixel count exceeds bounded pilot budget")
        provenance = [dict(row) for row in db.execute("""SELECT DISTINCT provider,source_url,rights_url
                  FROM pixel_observations ORDER BY provider,source_url,rights_url""")]
        pixels = db.execute("""SELECT provider,observed_at,first_captured_at,first_scan_at,
                                   latitude,longitude FROM pixel_observations
                            ORDER BY source_record_id""")
        scan_lookup = {scan["scan_at"]: i for i, scan in enumerate(scans)}
        row_map = {(i, region["region_id"]): {
            "scan_index": i, "scan_at": scan["scan_at"], "region_id": region["region_id"],
            "new_raw_pixels": 0, "new_candidate_cell_hours": 0,
            "sensor_raw_pixels": {source: 0 for source in FIRMS_SOURCES},
            "first_observed_at": None, "last_observed_at": None}
                   for i, scan in enumerate(scans) for region in chosen}
        grouped = defaultdict(set)
        daily_counts = Counter()
        daily_groups = defaultdict(set)
        selected = 0
        for pixel in pixels:
            source = pixel["provider"]
            observed, captured = _utc(pixel["observed_at"]), _utc(pixel["first_captured_at"])
            scan_index = scan_lookup.get(pixel["first_scan_at"])
            if source not in FIRMS_SOURCES or scan_index is None or not observed <= captured <= _utc(scans[scan_index]["captured_at"]):
                raise ValueError("pixel provenance or temporal availability contradicts receipt")
            latitude, longitude = pixel["latitude"], pixel["longitude"]
            if not math.isfinite(latitude) or not math.isfinite(longitude) or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError("pixel coordinate outside WGS84 range")
            region = next((r for r in chosen if distance_km(latitude, longitude,
                          r["latitude"], r["longitude"]) <= r["radius_km"]), None)
            if region is None:
                continue
            selected += 1
            rid = region["region_id"]
            row = row_map[(scan_index, rid)]
            row["new_raw_pixels"] += 1
            row["sensor_raw_pixels"][source] += 1
            time = observed.isoformat()
            if row["first_observed_at"] is None or time < row["first_observed_at"]:
                row["first_observed_at"] = time
            if row["last_observed_at"] is None or time > row["last_observed_at"]:
                row["last_observed_at"] = time
            hour = observed.replace(minute=0, second=0, microsecond=0).isoformat()
            cell = (math.floor(latitude * 20), math.floor(((longitude + 180) % 360 - 180) * 20), hour)
            grouped[(scan_index, rid)].add(cell)
            day_key = (rid, observed.date().isoformat())
            daily_counts[day_key] += 1
            daily_groups[day_key].add(cell)
    first_seen_cell_hours = set()
    for key in sorted(row_map):
        region_cells = {(key[1], cell) for cell in grouped[key]}
        row_map[key]["new_candidate_cell_hours"] = len(region_cells - first_seen_cell_hours)
        first_seen_cell_hours.update(region_cells)
    scan_rows = [row_map[key] for key in sorted(row_map)]
    daily = [{"region_id": rid, "observed_date": day,
              "new_raw_pixels": daily_counts[(rid, day)],
              "new_candidate_cell_hours": len(daily_groups[(rid, day)]),
              "archive_period_complete": False}
             for rid, day in sorted(daily_counts)]
    _rolling_rows(daily)
    report = {
        "schema_version": 1,
        "title": "Archived FIRMS thermal candidate activity pilot",
        "observation_unit": "new 0.05-degree cell by observed UTC hour, first archived in a scan",
        "regions": chosen, "heldout_region_ids": heldout,
        "source_receipts": scans, "source_provenance": provenance,
        "input_population": {"verified_scan_receipts": len(scans),
                             "unique_raw_pixels": count,
                             "selected_region_raw_pixels": selected,
                             "outside_selected_regions_raw_pixels": count - selected},
        "scan_rows": scan_rows, "daily_rows": daily,
        "weekly_rows": _period_rows(daily, "week"),
        "monthly_rows": _period_rows(daily, "month"),
        "satellite_opportunity_verified": False, "verified_fire_count": None,
        "coverage_warning": "Receipt completion verifies collection attempts, not satellite observation opportunity. "
                            "No detection is not evidence of no wildfire; observed periods are incomplete.",
        "model_research": evaluate_capture_model(scan_rows, scans, heldout),
    }
    report["evidence_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()
    if len(_canonical(report)) > MAX_REPORT_BYTES:
        raise ValueError("aggregate report exceeds static artifact budget")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixel-db", required=True, type=Path)
    parser.add_argument("--regions-json", required=True, type=Path)
    parser.add_argument("--holdout-region", action="append", required=True)
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    if args.output_json.exists() or args.output_json.is_symlink():
        parser.error("refusing to overwrite existing report")
    regions = json.loads(args.regions_json.read_text())
    report = build_capture_pilot(args.pixel_db, regions,
                                 heldout_region_ids=args.holdout_region)
    args.output_json.write_bytes(_canonical(report))
    print(json.dumps({"output": str(args.output_json),
                      "evidence_sha256": report["evidence_sha256"],
                      "model_status": report["model_research"]["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
