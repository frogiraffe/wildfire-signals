"""Bounded retrospective FIRMS country-CSV and GHCNh annual station study.

Standard FIRMS country CSVs are a different archive from our NRT scan receipts.
Both are thermal candidates. A full country file is not an acquisition mask, and
an absent record is never an observed negative. Raw sources stay outside Git.
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
import re
import sqlite3
from statistics import median
import tempfile
from urllib.parse import urlparse

from .environmental_analytics import DATA_USE, SOURCE_DOC, VARIABLES, read_station_file
from .historical_rollup import _bytes
from .observational_cohort import validate_regions
from .region_diagnostics import distance_km

SOURCES = {"VIIRS_NOAA20_STANDARD": ("viirs-jpss1", "N20"),
           "VIIRS_SNPP_STANDARD": ("viirs-snpp", "N")}
FIRMS_RIGHTS = "https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy"
FIRMS_ATTRIBUTES = "https://firms.modaps.eosdis.nasa.gov/content/descriptions/FIRMS_VIIRS_Firehotspots.html"
PIXEL_FIELDS = {"latitude", "longitude", "bright_ti4", "scan", "track", "acq_date",
                "acq_time", "satellite", "instrument", "confidence", "version",
                "bright_ti5", "frp", "daynight", "type"}
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_SELECTED_PIXELS = 100_000


def _asset_path(raw_dir: Path, asset: dict) -> Path:
    name = asset.get("filename")
    if not isinstance(name, str) or name != Path(name).name or name.startswith("."):
        raise ValueError("invalid source filename")
    path = raw_dir / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("missing or oversized source asset")
    size = asset.get("size_bytes")
    if type(size) is not int or size != path.stat().st_size:
        raise ValueError("source byte count differs")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != asset.get("sha256"):
        raise ValueError("source SHA-256 differs")
    revision = datetime.fromisoformat(asset["source_last_modified"])
    if revision.tzinfo is None or revision.utcoffset() != timedelta(0):
        raise ValueError("source last-modified must be UTC")
    return path


def _validate_manifest(manifest: dict) -> tuple[dict, dict, list[int]]:
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported annual study manifest")
    regions = validate_regions([manifest["region"]])
    region = regions[0]
    station = manifest["station"]
    if (station.get("region_id") != region["region_id"] or
        distance_km(station["latitude"], station["longitude"],
                    region["latitude"], region["longitude"]) > region["radius_km"]):
        raise ValueError("station outside declared study region")
    verified = datetime.fromisoformat(manifest["verified_at"])
    if verified.tzinfo is None or verified.utcoffset() != timedelta(0):
        raise ValueError("verification time must be UTC")
    label = manifest.get("country_file_label")
    if not isinstance(label, str) or not re.fullmatch(r"[A-Za-z][A-Za-z_]{0,79}", label):
        raise ValueError("invalid FIRMS country file label")
    thermal, weather = manifest.get("thermal_assets"), manifest.get("weather_assets")
    if not isinstance(thermal, list) or not isinstance(weather, list) or not thermal or not weather:
        raise ValueError("annual study sources missing")
    if any(type(item.get("year")) is not int for item in thermal):
        raise ValueError("source years must be integers")
    years = sorted({item["year"] for item in thermal})
    if (len(years) > 5 or years != list(range(years[0], years[-1] + 1)) or
        any(type(year) is not int or year < 2012 or year > verified.year for year in years) or
        len(thermal) != len(years) * len(SOURCES) or len(weather) != len(years)):
        raise ValueError("require two VIIRS sources and one station file per consecutive year")
    seen = set()
    for item in thermal:
        provider, year = item.get("provider"), item.get("year")
        if provider not in SOURCES or type(year) is not int or (provider, year) in seen:
            raise ValueError("duplicate or unsupported thermal provider/year")
        seen.add((provider, year))
        family, _ = SOURCES[provider]
        url = urlparse(item.get("source_url", ""))
        expected = f"/data/country/{family}/{year}/{family}_{year}_{label}.csv"
        if (url.scheme != "https" or url.hostname not in
            {"firms.modaps.eosdis.nasa.gov", "firms2.modaps.eosdis.nasa.gov"}
            or url.path != expected or url.query or url.fragment):
            raise ValueError("FIRMS source URL contract differs")
    seen_years = set()
    for item in weather:
        year = item.get("year")
        if item.get("provider") != "GHCNh" or type(year) is not int or year in seen_years:
            raise ValueError("duplicate or unsupported station year")
        seen_years.add(year)
        url = urlparse(item.get("source_url", ""))
        suffix = f"/{year}/psv/GHCNh_{station['id']}_{year}.psv"
        if (url.scheme != "https" or url.hostname != "www.ncei.noaa.gov" or
            not url.path.endswith(suffix) or url.query or url.fragment):
            raise ValueError("GHCNh source URL contract differs")
    if seen_years != set(years):
        raise ValueError("GHCNh years differ from FIRMS years")
    return region, station, years


def _acquisition(row: dict, year: int, satellite: str) -> datetime:
    if (row["satellite"] != satellite or row["instrument"] != "VIIRS" or
        row["version"] != "2" or row["confidence"] not in {"l", "n", "h"} or
        row["daynight"] not in {"D", "N"} or row["type"] not in {"0", "1", "2", "3"}):
        raise ValueError("FIRMS sensor, standard version or quality domain differs")
    try:
        observed = datetime.strptime(row["acq_date"] + row["acq_time"].zfill(4),
                                     "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc)
        lat, lon, frp = float(row["latitude"]), float(row["longitude"]), float(row["frp"])
    except (ValueError, TypeError):
        raise ValueError("invalid FIRMS acquisition or numeric source field") from None
    if (observed.year != year or not math.isfinite(lat) or not math.isfinite(lon) or
        not -90 <= lat <= 90 or not -180 <= lon <= 180 or
        not math.isfinite(frp) or frp < 0):
        raise ValueError("FIRMS coordinate, year or FRP outside source domain")
    return observed


def build_annual_study(manifest: dict, raw_dir: str | Path) -> dict:
    """Verify source files, stream all country rows and join positive hours only."""
    region, station, years = _validate_manifest(manifest)
    raw_dir = Path(raw_dir)
    if raw_dir.is_symlink() or not raw_dir.is_dir():
        raise ValueError("raw source directory missing")
    source_summaries = []
    population = Counter()
    daily = defaultdict(lambda: {"raw_pixels": 0, "cells": set(), "hours": set()})
    monthly = defaultdict(lambda: {"raw_pixels": 0, "cells": set(), "hours": set(), "days": set()})
    by_provider_hour = defaultdict(lambda: {"raw_pixels": 0, "cells": set(), "first_minute": None})
    with tempfile.TemporaryDirectory(prefix="ws-annual-dedup-") as temp:
        with closing(sqlite3.connect(Path(temp) / "dedup.sqlite3")) as dedup:
            dedup.execute("CREATE TABLE fingerprints(asset INTEGER, digest TEXT, PRIMARY KEY(asset,digest))")
            for asset_index, asset in enumerate(sorted(manifest["thermal_assets"],
                                                       key=lambda item: (item["year"], item["provider"]))):
                path = _asset_path(raw_dir, asset)
                year, provider = asset["year"], asset["provider"]
                _, satellite = SOURCES[provider]
                summary = {key: asset[key] for key in ("provider", "year", "source_url",
                           "size_bytes", "sha256", "source_last_modified")}
                summary.update({"source_rows": 0, "duplicate_rows": 0,
                                "selected_raw_pixels": 0, "first_observed_at": None,
                                "last_observed_at": None})
                with path.open(newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    if not PIXEL_FIELDS <= set(reader.fieldnames or []) or len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
                        raise ValueError("FIRMS country CSV schema differs")
                    for row in reader:
                        summary["source_rows"] += 1
                        observed = _acquisition(row, year, satellite)
                        stamp = observed.isoformat()
                        summary["first_observed_at"] = min(summary["first_observed_at"] or stamp, stamp)
                        summary["last_observed_at"] = max(summary["last_observed_at"] or stamp, stamp)
                        digest = hashlib.sha256(_bytes({key: row[key] for key in PIXEL_FIELDS})).hexdigest()
                        inserted = dedup.execute("INSERT OR IGNORE INTO fingerprints VALUES(?,?)",
                                                 (asset_index, digest))
                        if not inserted.rowcount:
                            summary["duplicate_rows"] += 1
                            continue
                        lat, lon = float(row["latitude"]), float(row["longitude"])
                        if distance_km(lat, lon, region["latitude"], region["longitude"]) > region["radius_km"]:
                            continue
                        population["selected_raw_pixels"] += 1
                        summary["selected_raw_pixels"] += 1
                        if population["selected_raw_pixels"] > MAX_SELECTED_PIXELS:
                            raise ValueError("selected study exceeds bounded report budget; narrow region")
                        hour = observed.replace(minute=0, second=0, microsecond=0).isoformat()
                        day, month = observed.date().isoformat(), observed.strftime("%Y-%m")
                        cell = (math.floor(lat * 20), math.floor(((lon + 180) % 360 - 180) * 20))
                        daily[(day, provider)]["raw_pixels"] += 1
                        daily[(day, provider)]["cells"].add((cell, hour))
                        daily[(day, provider)]["hours"].add(hour)
                        monthly[(month, provider)]["raw_pixels"] += 1
                        monthly[(month, provider)]["cells"].add((cell, hour))
                        monthly[(month, provider)]["hours"].add(hour)
                        monthly[(month, provider)]["days"].add(day)
                        unit = by_provider_hour[(provider, hour)]
                        unit["raw_pixels"] += 1
                        unit["cells"].add(cell)
                        unit["first_minute"] = min(unit["first_minute"] or observed, observed)
                if not summary["source_rows"]:
                    raise ValueError("empty FIRMS country file is not evidence of no detections")
                population["country_source_rows"] += summary["source_rows"]
                population["duplicate_source_rows"] += summary["duplicate_rows"]
                source_summaries.append(summary)
            dedup.commit()
    weather_summaries, weather_monthly, candidate_hours = [], [], []
    for asset in sorted(manifest["weather_assets"], key=lambda item: item["year"]):
        path = _asset_path(raw_dir, asset)
        year = asset["year"]
        observations, counts, digest = read_station_file(path, station,
                                               start=date(year,1,1), end=date(year,12,31))
        if digest != asset["sha256"]:
            raise ValueError("GHCNh source SHA-256 differs")
        weather_summaries.append({**{key: asset[key] for key in ("provider", "year", "source_url",
            "size_bytes", "sha256", "source_last_modified")}, **counts,
            "first_observed_at": observations[0]["observed_at"] if observations else None,
            "last_observed_at": observations[-1]["observed_at"] if observations else None})
        population["station_source_rows"] += counts["source_rows"]
        times = [row["time"] for row in observations]
        station_by_month = defaultdict(list)
        for row in observations:
            station_by_month[row["observed_at"][:7]].append(row)
        for month in (f"{year}-{index:02d}" for index in range(1,13)):
            subset = station_by_month[month]
            weather_monthly.append({"observed_month": month, "station_rows": len(subset),
                 **{f"{name}_median": median(values) if values else None
                    for name, _, _ in VARIABLES.values()
                    if name != "wind_direction_deg"
                    for values in [[row[name] for row in subset if row[name] is not None]]},
                 **{f"{name}_n": sum(row[name] is not None for row in subset)
                    for name, _, _ in VARIABLES.values() if name != "wind_direction_deg"}})
        for (provider, hour), unit in sorted(by_provider_hour.items()):
            first = unit["first_minute"]
            if first.year != year:
                continue
            index = bisect_right(times, first) - 1
            weather = (observations[index] if index >= 0 and
                       first - times[index] <= timedelta(minutes=60) else None)
            item = {"provider": provider, "observed_hour": hour,
                    "first_candidate_minute": first.isoformat(),
                    "raw_pixels": unit["raw_pixels"], "candidate_cell_hours": len(unit["cells"]),
                    "weather_observed_at": weather["observed_at"] if weather else None,
                    "satellite_observation_opportunity": "unknown"}
            for _, (name, _, _) in VARIABLES.items():
                item[name] = weather[name] if weather else None
                if item[name] is not None:
                    population[f"weather_matched_provider_hours_{name}"] += 1
            candidate_hours.append(item)
    daily_rows = [{"observed_date": day, "provider": provider,
                   "raw_pixels": counts["raw_pixels"],
                   "candidate_cell_hours": len(counts["cells"]),
                   "candidate_hours": len(counts["hours"]),
                   "satellite_observation_opportunity": "unknown"}
                  for (day, provider), counts in sorted(daily.items())]
    monthly_rows = [{"observed_month": f"{year}-{month:02d}", "provider": provider,
                     "raw_pixels": counts["raw_pixels"],
                     "candidate_cell_hours": len(counts["cells"]),
                     "days_with_archived_candidates": len(counts["days"]),
                     "satellite_observation_opportunity": "unknown"}
                    for year in years for month in range(1,13) for provider in SOURCES
                    for counts in [monthly[(f"{year}-{month:02d}", provider)]]]
    population.update({"source_files": len(source_summaries),
                       "weather_files": len(weather_summaries),
                       "candidate_provider_hours": len(candidate_hours),
                       "days_with_archived_candidates": len({row["observed_date"] for row in daily_rows})})
    report = {"schema_version": 1, "status": "retrospective_standard_archive_exploration",
              "country_file_label": manifest["country_file_label"], "region": region,
              "station": station, "start_date": f"{years[0]}-01-01",
              "end_date": f"{years[-1]}-12-31", "verified_at": manifest["verified_at"],
              "thermal_source": "NASA FIRMS standard-processing VIIRS country CSV",
              "thermal_source_attributes": FIRMS_ATTRIBUTES, "thermal_source_rights": FIRMS_RIGHTS,
              "thermal_first_available_at": None,
              "weather_source": "NOAA NCEI GHCNh annual fixed-station PSV",
              "weather_source_documentation": SOURCE_DOC, "weather_data_use": DATA_USE,
              "weather_license": "CC0-1.0", "environment_first_available_at": None,
              "weather_spatial_support": "single fixed station, not pixel weather",
              "weather_temporal_support": "latest prior station record within 60 min at first candidate minute",
              "weather_units": {"temperature_c": "degree Celsius", "wind_speed_m_s": "metres per second",
                                "wind_direction_deg": "degrees clockwise from north",
                                "relative_humidity_pct": "percent"},
              "source_asset_manifest": source_summaries,
              "weather_asset_manifest": weather_summaries,
              "population": dict(population), "daily_rows": daily_rows,
              "monthly_rows": monthly_rows, "weather_monthly_rows": weather_monthly,
              "candidate_provider_hours": sorted(candidate_hours,
                                                  key=lambda row: (row["observed_hour"], row["provider"])),
              "observation_opportunity_verified": False, "no_detection_count": None,
              "independent_fire_outcome_valid": False,
              "statistical_relationship_supported": False,
              "interpretation": "Monthly numbers count archived thermal candidate pixels and cell-hours, not fires or rates. A zero archived row count is not an observed no-fire hour. Sensor acquisition, clouds and collection changes are unmeasured. Station values are retrospective context at one point, not weather at each pixel or decision-time forecast inputs. No weather association or wildfire model is inferred."}
    report["evidence_sha256"] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("output must be a new file")
    report = build_annual_study(json.loads(args.manifest.read_text()), args.raw_dir)
    args.output.write_bytes(_bytes(report))
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "population": report["population"]}, sort_keys=True))


if __name__ == "__main__": main()
