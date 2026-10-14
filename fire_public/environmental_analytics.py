"""Retrospective GHCNh station context for archived FIRMS thermal candidates.

This is a bounded descriptive join, not an acquisition mask, fire label or forecast.
The station is a fixed point; its conditions are not asserted at every pixel.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from contextlib import closing
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import mean, median
from urllib.parse import urlparse

from .historical_rollup import _bytes, _study, MAX_QUERY_DAYS
from .historical_signal_analysis import _read_only
from .observation_opportunity import STATES, classify_interval

SOURCE_DOC = "https://www.ncei.noaa.gov/products/global-historical-climatology-network-hourly"
DATA_USE = "https://www.ncei.noaa.gov/access/metadata/landing-page/bin/iso?id=gov.noaa.ncdc%3AC01688"
VARIABLES = {"temperature": ("temperature_c", -100, 65),
             "wind_speed": ("wind_speed_m_s", 0, 150),
             "wind_direction": ("wind_direction_deg", 0, 360),
             "relative_humidity": ("relative_humidity_pct", 0, 100)}
QC_PASSED_ONE_SOURCES = {"220", "221", "222", "223", "313", "314", "315",
                         "322", "335", "343", "344", "346", "347", "348"}
QC_PASSED_FIVE_SOURCES = {"313", "314", "315", "322", "335", "343", "344", "346"}


def _quality_accepted(row: dict, source_name: str) -> bool:
    """GHCNh QC meanings depend on the source; a nonblank code can mean passed."""
    code = row[f"{source_name}_Quality_Code"].strip()
    source = row.get(f"{source_name}_Source_Code", "").strip()
    return (not code or (code == "1" and source in QC_PASSED_ONE_SOURCES)
            or (code == "5" and source in QC_PASSED_FIVE_SOURCES)
            or (code == "0" and source == "345"))


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        raise ValueError("GHCNh source DATE must be UTC without an offset")
    return parsed.replace(tzinfo=timezone.utc)


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_station_file(path: str | Path, station: dict, *, start: date,
                      end: date) -> tuple[list[dict], dict, str]:
    """Stream one GHCNh PSV; validate station, time order and per-value quality."""
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(path)
    digest = _source_hash(path)
    selected = []
    exclusions = Counter()
    undefined_wind_direction = 0
    source_rows = 0
    last = None
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        required = {"STATION", "Station_name", "DATE", "LATITUDE", "LONGITUDE",
                    "ELEVATION", *VARIABLES}
        required.update(f"{key}_Quality_Code" for key in VARIABLES)
        if not required <= set(reader.fieldnames or []):
            raise ValueError("GHCNh weather schema missing required fields")
        for row in reader:
            source_rows += 1
            if row["STATION"] != station["id"] or row["Station_name"].upper() != station["name"].upper():
                raise ValueError("GHCNh station identity changed")
            if (abs(float(row["LATITUDE"]) - station["latitude"]) > .01 or
                abs(float(row["LONGITUDE"]) - station["longitude"]) > .01 or
                abs(float(row["ELEVATION"]) - station["elevation_m"]) > 5):
                raise ValueError("GHCNh station coordinates or elevation changed")
            observed = _utc(row["DATE"])
            if last is not None and observed <= last:
                raise ValueError("GHCNh weather rows are unordered or duplicated")
            last = observed
            if not start <= observed.date() <= end:
                continue
            result = {"observed_at": observed.isoformat(), "time": observed}
            for source_name, (name, minimum, maximum) in VARIABLES.items():
                raw = row[source_name].strip()
                if not raw:
                    result[name] = None
                elif not _quality_accepted(row, source_name):
                    exclusions[source_name] += 1
                    result[name] = None
                elif (source_name == "wind_direction" and raw == "999" and
                      row.get("wind_direction_Measurement_Code", "").strip() in {"V", "C"}):
                    undefined_wind_direction += 1
                    result[name] = None
                else:
                    value = float(raw)
                    if not math.isfinite(value) or not minimum <= value <= maximum:
                        raise ValueError(f"invalid GHCNh {source_name} value")
                    result[name] = value
            selected.append(result)
    counts = {"source_rows": source_rows, "weather_rows_in_range": len(selected),
              "quality_exclusions": dict(exclusions)}
    if undefined_wind_direction:
        counts["undefined_wind_direction_rows"] = undefined_wind_direction
    return selected, counts, digest


def build_station_context(pixel_db: str | Path, regions: list[dict], weather_file: str | Path,
                          station: dict, *, start_date: str, end_date: str,
                          source_url: str, source_last_modified: str,
                          expected_source_sha256: str | None = None) -> dict:
    """Join candidate cell-hours to latest earlier station row at most 60 min old.

    No non-candidate hour is assigned a zero. Retrospective file modification time
    does not establish when an individual observation first became available.
    """
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end - start).days >= MAX_QUERY_DAYS:
        raise ValueError("query must cover 1..366 UTC dates")
    if start.year != end.year:
        raise ValueError("one station-year source is required per annual query")
    revision = datetime.fromisoformat(source_last_modified)
    if revision.tzinfo is None:
        raise ValueError("source last-modified must include UTC offset")
    parsed_url = urlparse(source_url)
    if (parsed_url.scheme != "https" or parsed_url.hostname != "www.ncei.noaa.gov" or
        not parsed_url.path.endswith(f"/{start.year}/psv/GHCNh_{station['id']}_{start.year}.psv")):
        raise ValueError("source URL must identify the official GHCNh station/year file")
    study_id, chosen, contract = _study(regions)
    if len(chosen) != 1 or chosen[0]["region_id"] != station.get("region_id", chosen[0]["region_id"]):
        raise ValueError("station pilot requires one explicit region")
    rows, source_counts, weather_hash = read_station_file(weather_file, station,
                                                          start=start, end=end)
    if expected_source_sha256 is not None and weather_hash != expected_source_sha256:
        raise ValueError("GHCNh source SHA-256 differs from pinned asset")
    if rows and revision.astimezone(timezone.utc) < rows[-1]["time"]:
        raise ValueError("GHCNh source revision predates selected observations")
    times = [item["time"] for item in rows]
    upper = (end + timedelta(days=1)).isoformat() + "T"
    lower = start.isoformat() + "T"
    with closing(_read_only(Path(pixel_db))) as db:
        study = db.execute("SELECT contract_json,state FROM analytics_studies WHERE study_id=?",
                           (study_id,)).fetchone()
        if not study or study["contract_json"] != contract or study["state"] != "ready":
            raise ValueError("historical rollup is missing or building")
        candidates = db.execute("""SELECT observed_hour,COUNT(*) AS candidate_cell_hours,
               MIN(first_captured_at) AS first_captured_at,
               MAX(first_captured_at) AS last_captured_at
               FROM analytics_cell_hours WHERE study_id=? AND region_id=?
               AND observed_hour>=? AND observed_hour<? GROUP BY observed_hour
               ORDER BY observed_hour""",
               (study_id, chosen[0]["region_id"], lower, upper)).fetchall()
        raw = db.execute("""SELECT substr(observed_at,1,13) AS hour,COUNT(*) AS n
               FROM analytics_region_pixels WHERE study_id=? AND region_id=?
               AND observed_at>=? AND observed_at<? GROUP BY hour""",
               (study_id, chosen[0]["region_id"], lower, upper)).fetchall()
        scans = [dict(row) for row in db.execute("""SELECT scan_at,receipt_sha256,
               asset_manifest_sha256,source_states_json FROM analytics_processed_scans
               WHERE study_id=? ORDER BY scan_at""", (study_id,))]
        assets = [dict(row) for row in db.execute("""SELECT a.scan_at,a.asset_name,
               a.asset_sha256,a.rows_seen FROM pixel_scan_assets AS a
               JOIN analytics_processed_scans AS s ON s.scan_at=a.scan_at
               WHERE s.study_id=? ORDER BY a.scan_at,a.asset_name""", (study_id,))]
        source_provenance = [dict(row) for row in db.execute("""SELECT DISTINCT
               p.provider,p.source_url,p.rights_url FROM analytics_region_pixels AS r
               JOIN pixel_observations AS p ON p.source_record_id=r.source_record_id
               WHERE r.study_id=? AND r.region_id=? AND r.observed_at>=? AND r.observed_at<?
               ORDER BY p.provider,p.source_url,p.rights_url""",
               (study_id,chosen[0]["region_id"],lower,upper))]
    raw_by_hour = {item["hour"]: item["n"] for item in raw}
    candidate_hours = []
    matched = Counter()
    for candidate in candidates:
        observed = datetime.fromisoformat(candidate["observed_hour"])
        index = bisect_right(times, observed) - 1
        weather = rows[index] if index >= 0 and observed - times[index] <= timedelta(minutes=60) else None
        joined = {"observed_hour": candidate["observed_hour"],
                  "candidate_cell_hours": candidate["candidate_cell_hours"],
                  "raw_pixels": raw_by_hour.get(candidate["observed_hour"][:13], 0),
                  "first_captured_at": candidate["first_captured_at"],
                  "last_captured_at": candidate["last_captured_at"],
                  "weather_observed_at": weather["observed_at"] if weather else None,
                  "station_distance_contract_km": chosen[0]["radius_km"],
                  "observation_state": classify_interval(archived_candidates=candidate["candidate_cell_hours"],
                                                         retrieval=None),
                  "satellite_observation_opportunity": "unknown"}
        for field, (name, _, _) in VARIABLES.items():
            joined[name] = weather[name] if weather else None
            if joined[name] is not None:
                matched[field] += 1
        candidate_hours.append(joined)
    by_hour = {}
    for row in rows:
        by_hour[row["observed_at"][:13]] = row
    weather_hourly = []
    for key, row in sorted(by_hour.items()):
        weather_hourly.append({"hour": key + ":00:00+00:00",
                               "weather_observed_at": row["observed_at"],
                               **{name: row[name] for name, _, _ in VARIABLES.values()},
                               "candidate_cell_hours": next((c["candidate_cell_hours"]
                                     for c in candidate_hours if c["observed_hour"][:13] == key), None)})
    for scan in scans:
        scan["source_states"] = json.loads(scan.pop("source_states_json"))
    descriptive = {}
    for _, (name, _, _) in VARIABLES.items():
        station_values = [row[name] for row in rows if row[name] is not None]
        candidate_values = [row[name] for row in candidate_hours if row[name] is not None]
        descriptive[name] = {
            "station_observation_n": len(station_values),
            "station_min": min(station_values) if station_values else None,
            "station_max": max(station_values) if station_values else None,
            "station_mean": round(mean(station_values), 3)
                if station_values and name != "wind_direction_deg" else None,
            "matched_candidate_hour_n": len(candidate_values),
            "matched_candidate_hour_median": median(candidate_values)
                if candidate_values and name != "wind_direction_deg" else None,
            "circular_direction_statistic_withheld": name == "wind_direction_deg",
            "candidate_hours_are_not_independent_pixels": True}
    report = {"schema_version": 1, "status": "retrospective_descriptive_exploration",
              "region": chosen[0], "station": station,
              "start_date": start.isoformat(), "end_date": end.isoformat(),
              "pixel_study_id": study_id,
              "thermal_source": "NASA FIRMS VIIRS NOAA-20/21 NRT original pixel archive",
              "weather_source": "NOAA NCEI GHCNh fixed station, annual PSV",
              "weather_source_documentation": SOURCE_DOC,
              "weather_documentation_version": "GHCNh documentation 1.1.0, 2026-03-10",
              "weather_data_use": DATA_USE, "weather_license": "CC0-1.0",
              "weather_source_url": source_url,
              "weather_source_last_modified": revision.astimezone(timezone.utc).isoformat(),
              "source_sha256": weather_hash,
              "environment_first_available_at": None,
              "weather_units": {"temperature_c": "degree Celsius", "wind_speed_m_s": "metres per second",
                                "wind_direction_deg": "degrees clockwise from north",
                                "relative_humidity_pct": "percent"},
              "weather_spatial_support": "single fixed station; no pixel-level weather observation",
              "weather_temporal_support": "irregular station observations; latest prior record within 60 min",
              "population": {"candidate_hours": len(candidate_hours),
                             "candidate_cell_hours": sum(c["candidate_cell_hours"] for c in candidate_hours),
                             "raw_pixels": sum(c["raw_pixels"] for c in candidate_hours),
                             **source_counts,
                             **{f"matched_candidate_hours_{name}": matched[field]
                                for field, (name, _, _) in VARIABLES.items()}},
              "weather_quality_exclusions": source_counts["quality_exclusions"],
              "descriptive_statistics": descriptive,
              "candidate_hours": candidate_hours, "weather_hourly": weather_hourly,
              "source_receipts": scans, "source_asset_manifest": assets,
              "thermal_source_provenance": source_provenance,
              "observation_opportunity_verified": False,
              "observation_state_schema_version": 1, "observation_state_contract": STATES,
              "independent_fire_outcome_valid": False,
              "statistical_relationship_supported": False,
              "interpretation": "Station context for archived candidate hours only. Other hours are unknown satellite exposure; no correlation, fire rate or weather effect is estimated. Station selection followed inspection of pilot candidate counts."}
    report["evidence_sha256"] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pixel-db", required=True, type=Path)
    parser.add_argument("--regions-json", required=True, type=Path)
    parser.add_argument("--weather-psv", required=True, type=Path)
    parser.add_argument("--station-json", required=True, type=Path)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-last-modified", required=True)
    parser.add_argument("--expected-weather-sha256", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    if args.output_json.exists() or args.output_json.is_symlink():
        parser.error("output must be a new file")
    report = build_station_context(args.pixel_db, json.loads(args.regions_json.read_text()),
              args.weather_psv, json.loads(args.station_json.read_text()),
              start_date=args.start_date, end_date=args.end_date, source_url=args.source_url,
              source_last_modified=args.source_last_modified,
              expected_source_sha256=args.expected_weather_sha256)
    args.output_json.write_bytes(_bytes(report))
    print(json.dumps({"evidence_sha256": report["evidence_sha256"],
                      "population": report["population"]}, sort_keys=True))


if __name__ == "__main__":
    main()
