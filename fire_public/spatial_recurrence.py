"""Bounded positive-only spatial recurrence from verified original FIRMS pixels.

0.01 degree WGS84 bins are descriptive groups, not sensor footprints, event
identities, independently observed static sources, or no-detection cells.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import closing
import csv
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import tempfile

from .annual_country_analytics import (_acquisition, _asset_path, _validate_manifest,
                                       FIRMS_ATTRIBUTES, FIRMS_RIGHTS, MAX_SELECTED_PIXELS,
                                       PIXEL_FIELDS, SOURCES)
from .historical_rollup import _bytes
from .observational_cohort import validate_regions
from .region_diagnostics import distance_km

GRID_DEGREES = 0.01
MAX_PUBLISHED_BINS = 20


def _bin_key(lat: float, lon: float) -> tuple[int, int]:
    return math.floor(lat * 100), math.floor(((lon + 180) % 360 - 180) * 100)


def _cell() -> dict:
    return {"raw_pixels": 0, "dates": set(), "years": set(), "providers": Counter(),
            "providers_by_date": defaultdict(set), "pixels_by_date": Counter(),
            "confidence": Counter(), "daynight": Counter(), "types": Counter(),
            "first": None, "last": None}


def _classification(item: dict) -> str:
    # This is a bounded research queue rule, not a physical-source diagnosis.
    if (len(item["years"]) >= 2 and len(item["dates"]) >= 12 and
        item["types"]["2"] * 2 >= item["raw_pixels"]):
        return "potential_static_thermal_source"
    return ("recurrently_observed_candidate" if len(item["dates"]) >= 2
            else "observed_thermal_candidate")


def build_spatial_recurrence(manifest: dict, regions: list[dict], raw_dir: str | Path) -> dict:
    """Verify files, stream pixels once, publish bounded coarsened-bin evidence."""
    _, _, years = _validate_manifest(manifest)
    chosen = validate_regions(regions)
    if not chosen or len(chosen) > 8:
        raise ValueError("require one to eight selected regions")
    for index, left in enumerate(chosen):
        for right in chosen[index + 1:]:
            if distance_km(left["latitude"], left["longitude"],
                           right["latitude"], right["longitude"]) <= left["radius_km"] + right["radius_km"]:
                raise ValueError("selected regions overlap; source pixels cannot have an unambiguous region")
    raw_dir = Path(raw_dir)
    if raw_dir.is_symlink() or not raw_dir.is_dir():
        raise ValueError("raw source directory missing")
    bins = {region["region_id"]: defaultdict(_cell) for region in chosen}
    yearly = {region["region_id"]: defaultdict(lambda: {
        "raw_pixels": 0, "dates": set(), "providers": Counter(),
        "confidence": Counter(), "daynight": Counter(), "types": Counter()})
        for region in chosen}
    source_summaries = []
    population = Counter()
    with tempfile.TemporaryDirectory(prefix="ws-spatial-dedup-") as temp:
        with closing(sqlite3.connect(Path(temp) / "dedup.sqlite3")) as dedup:
            dedup.execute("CREATE TABLE fingerprints(asset INTEGER,digest TEXT,PRIMARY KEY(asset,digest))")
            for index, asset in enumerate(sorted(manifest["thermal_assets"],
                                                 key=lambda item: (item["year"], item["provider"]))):
                path = _asset_path(raw_dir, asset)
                provider, year = asset["provider"], asset["year"]
                summary = {key: asset[key] for key in ("provider", "year", "source_url",
                          "size_bytes", "sha256", "source_last_modified")}
                summary.update({"source_rows": 0, "duplicate_rows": 0,
                                "selected_by_region": {r["region_id"]: 0 for r in chosen}})
                with path.open(newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    if not PIXEL_FIELDS <= set(reader.fieldnames or []) or len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
                        raise ValueError("FIRMS country CSV schema differs")
                    for row in reader:
                        summary["source_rows"] += 1
                        observed = _acquisition(row, year, SOURCES[provider][1])
                        digest = hashlib.sha256(_bytes({key: row[key] for key in PIXEL_FIELDS})).hexdigest()
                        if not dedup.execute("INSERT OR IGNORE INTO fingerprints VALUES(?,?)",
                                             (index, digest)).rowcount:
                            summary["duplicate_rows"] += 1
                            continue
                        lat, lon = float(row["latitude"]), float(row["longitude"])
                        for region in chosen:
                            if distance_km(lat, lon, region["latitude"], region["longitude"]) > region["radius_km"]:
                                continue
                            region_id = region["region_id"]
                            population["selected_raw_pixels"] += 1
                            summary["selected_by_region"][region_id] += 1
                            if population["selected_raw_pixels"] > MAX_SELECTED_PIXELS:
                                raise ValueError("selected spatial study exceeds bounded budget")
                            entry = bins[region_id][_bin_key(lat, lon)]
                            date = observed.date().isoformat()
                            entry["raw_pixels"] += 1
                            entry["dates"].add(date)
                            entry["years"].add(year)
                            entry["providers"][provider] += 1
                            entry["providers_by_date"][date].add(provider)
                            entry["pixels_by_date"][date] += 1
                            entry["confidence"][row["confidence"]] += 1
                            entry["daynight"][row["daynight"]] += 1
                            entry["types"][row["type"]] += 1
                            entry["first"] = min(entry["first"] or observed, observed)
                            entry["last"] = max(entry["last"] or observed, observed)
                            annual = yearly[region_id][year]
                            annual["raw_pixels"] += 1
                            annual["dates"].add(date)
                            annual["providers"][provider] += 1
                            annual["confidence"][row["confidence"]] += 1
                            annual["daynight"][row["daynight"]] += 1
                            annual["types"][row["type"]] += 1
                if not summary["source_rows"]:
                    raise ValueError("empty FIRMS country file is not no-detection evidence")
                population["country_source_rows"] += summary["source_rows"]
                population["duplicate_source_rows"] += summary["duplicate_rows"]
                source_summaries.append(summary)
    region_reports = []
    for region in chosen:
        cells = bins[region["region_id"]]
        pixels = sum(item["raw_pixels"] for item in cells.values())
        recurrent = sum(len(item["dates"]) >= 2 for item in cells.values())
        repeated_across_years = sum(len(item["years"]) >= 2 for item in cells.values())
        same_day_both = sum(any(len(providers) >= 2 for providers in item["providers_by_date"].values())
                            for item in cells.values())
        ranked = sorted(((key, item) for key, item in cells.items() if item["raw_pixels"] >= 2),
                        key=lambda pair: (-len(pair[1]["dates"]), -pair[1]["raw_pixels"], pair[0]))
        published = []
        for (lat_bin, lon_bin), item in ranked[:MAX_PUBLISHED_BINS]:
            days = len(item["dates"])
            published.append({"bin_id": f"{lat_bin}:{lon_bin}",
                "bounds_wgs84": [lat_bin / 100, lon_bin / 100,
                                 (lat_bin + 1) / 100, (lon_bin + 1) / 100],
                "raw_pixels": item["raw_pixels"], "distinct_dates": days,
                "distinct_years": len(item["years"]),
                "first_observed_at": item["first"].isoformat(),
                "last_observed_at": item["last"].isoformat(),
                "span_days": (item["last"].date() - item["first"].date()).days,
                "sensor_agreement_dates": sum(len(providers) >= 2 for providers in item["providers_by_date"].values()),
                "provider_counts": dict(sorted(item["providers"].items())),
                "confidence_counts": dict(sorted(item["confidence"].items())),
                "daynight_counts": dict(sorted(item["daynight"].items())),
                "source_type_counts": dict(sorted(item["types"].items())),
                "max_single_date_pixel_share": round(max(item["pixels_by_date"].values()) / item["raw_pixels"], 4),
                "classification": _classification(item),
                "classification_basis": "research triage: >=12 dates, >=2 years, >=50% FIRMS type=2 pixels"
                  if _classification(item) == "potential_static_thermal_source" else
                  "archived detections on >=2 UTC dates" if days >= 2 else "archived detection only",
                "independently_classified": False,
                "source_identity_status": "unresolved"})
        confidence = Counter()
        daynight = Counter()
        source_types = Counter()
        for item in cells.values():
            confidence.update(item["confidence"])
            daynight.update(item["daynight"])
            source_types.update(item["types"])
        year_rows = []
        for year in years:
            item = yearly[region["region_id"]][year]
            year_rows.append({"year": year, "raw_pixels": item["raw_pixels"],
                "days_with_archived_candidates": len(item["dates"]),
                "provider_counts": dict(sorted(item["providers"].items())),
                "confidence_counts": dict(sorted(item["confidence"].items())),
                "daynight_counts": dict(sorted(item["daynight"].items())),
                "source_type_counts": dict(sorted(item["types"].items()))})
        region_reports.append({"region": region, "selected_raw_pixels": pixels,
            "occupied_bins": len(cells), "recurrently_observed_bins": recurrent,
            "bins_seen_in_multiple_years": repeated_across_years,
            "potential_static_source_bins": sum(_classification(item) == "potential_static_thermal_source"
                                                for item in cells.values()),
            "bins_with_same_day_both_sensors": same_day_both,
            "bins_with_only_one_observed_date": sum(len(item["dates"]) == 1 for item in cells.values()),
            "max_bin_raw_pixel_share": round(max((item["raw_pixels"] for item in cells.values()),
                                                   default=0) / pixels, 4) if pixels else None,
            "published_bins": published,
            "unpublished_bins": len(cells) - len(published),
            "yearly_quality_rows": year_rows,
            "confidence_counts": dict(sorted(confidence.items())),
            "daynight_counts": dict(sorted(daynight.items())),
            "source_type_counts": dict(sorted(source_types.items()))})
    population["source_files"] = len(source_summaries)
    population["unique_source_rows"] = population["country_source_rows"] - population["duplicate_source_rows"]
    report = {"schema_version": 1, "status": "descriptive_spatial_recurrence_only",
              "verified_at": manifest["verified_at"], "start_date": f"{years[0]}-01-01",
              "end_date": f"{years[-1]}-12-31", "grid_degrees_wgs84": GRID_DEGREES,
              "source_asset_manifest": source_summaries, "population": dict(population),
              "regions": region_reports, "source_attributes": FIRMS_ATTRIBUTES,
              "source_rights": FIRMS_RIGHTS,
              "static_thermal_anomalies_mask_reference":
                  "https://firms.modaps.eosdis.nasa.gov/descriptions/Static_Thermal_Anomalies_Mask.html",
              "static_mask_redistributed": False,
              "observation_opportunity_verified": False,
              "independent_static_source_evidence": False,
              "independent_fire_outcome_valid": False,
              "no_detection_count": None,
              "interpretation": "A recurring 0.01 degree bin is an archived spatial pattern, not proof of one physical source, an industrial site or wildfire. Potential-static is a conservative source-type-2 plus recurrence triage rule, not an independently confirmed non-vegetation label; the FIRMS historical type field has known defects. Same-day dual-sensor presence is not independent event confirmation. No absent bin is a verified no-detection."}
    report["evidence_sha256"] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--regions-json", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("output must be a new file")
    report = build_spatial_recurrence(json.loads(args.manifest.read_text()),
                                      json.loads(args.regions_json.read_text()), args.raw_dir)
    args.output.write_bytes(_bytes(report))
    print(json.dumps({"output": str(args.output),
                      "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      "population": report["population"]}, sort_keys=True))


if __name__ == "__main__":
    main()
