"""Reproducible multi-year research samples from REAL archived NIFC polygons.

Collects an explicitly bounded, seeded-hash sample of the government's
published ObjectIDs for each year. This is a sample of *records available at
the source*, never a complete inventory of wildfires and never negative labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import statistics
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .history import _timestamp
from .official_perimeters import (
    SERVICE, RIGHTS_URL, _canonical, _fetch, _rings, sync_year,
)

MAX_STUDY_YEARS = 8
MAX_STUDY_PER_YEAR = 30
MAX_STUDY_POLYGONS = 240
MAX_REPORT_FILE_BYTES = 20_000_000


def validate_years(years: list[int]) -> tuple[int, ...]:
    if (not isinstance(years, list) or not 1 <= len(years) <= MAX_STUDY_YEARS
            or any(type(y) is not int or not 1900 <= y <= 2019 for y in years)
            or len(set(years)) != len(years)):
        raise ValueError("1..8 unique historical US NIFC years, through 2019, required")
    return tuple(sorted(years))


def _readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"verified local NIFC archive required: {path}")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def study_report(db_path: str | Path, *, at: str, years: list[int],
                 required_batches: dict[int, str] | None = None) -> tuple[dict, dict]:
    """Rebuild deterministic report and source-preserving GeoJSON using local DB only.

    Selects the latest saved *batch* per year available by cutoff, rather
    than blending older and newer versions into an untraceable snapshot.
    """
    year_ids = validate_years(years)
    decision = _timestamp(at)
    samples = []
    features = []
    with closing(_readonly(Path(db_path))) as db:
        tables = {r["name"] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"perimeter_fetches", "perimeter_versions",
                "perimeter_sample_metadata"}.issubset(tables):
            raise ValueError("archive does not contain traceable NIFC sampled batches")
        for year in year_ids:
            batch_filter = (" AND f.batch_id=?" if required_batches is not None else "")
            lookup = (year, decision, required_batches[year]) if (
                required_batches is not None) else (year, decision)
            fetch = db.execute("""
                SELECT f.batch_id, f.captured_at, f.total_service_ids, f.selected_ids,
                       f.ids_sha256,f.subset_only,m.selection_mode,
                       m.selection_seed,m.selected_ids_sha256
                FROM perimeter_fetches f JOIN perimeter_sample_metadata m
                  ON m.batch_id=f.batch_id
                WHERE f.fire_year=? AND f.captured_at<=?""" + batch_filter +
                " ORDER BY f.captured_at DESC,f.batch_id DESC LIMIT 1", lookup).fetchone()
            if fetch is None:
                samples.append({
                    "fire_year": year, "archive_status": "not_captured_by_decision",
                    "source_object_ids": None, "sampled_polygons": 0,
                    "sample_fraction_of_published_ids": None,
                    "source_census_complete": False,
                    "evidence_availability": "unknown",
                })
                continue
            batch_id = fetch["batch_id"]
            rows = db.execute("""
                SELECT source_identity, object_id,fire_year,name,source_acres,
                       feature_sha256,geometry_json,attributes_json
                FROM perimeter_versions WHERE batch_id=? ORDER BY object_id
            """, (batch_id,)).fetchall()
            if len(rows) != fetch["selected_ids"]:
                raise ValueError("sample archive row count contradicts source manifest")
            if len(features) + len(rows) > MAX_STUDY_POLYGONS:
                raise ValueError("study report exceeds 240 geometry budget")
            actual_ids = [r["object_id"] for r in rows]
            if hashlib.sha256(_canonical(actual_ids).encode()).hexdigest() != fetch["selected_ids_sha256"]:
                raise ValueError("sample archive source IDs failed integrity check")
            names = []
            acreages = []
            attributes_present = {"INCIDENT": 0, "GIS_ACRES": 0, "GlobalID": 0}
            polygons = {"Polygon": 0, "MultiPolygon": 0}
            for row in rows:
                props = json.loads(row["attributes_json"])
                geometry = json.loads(row["geometry_json"])
                if (props.get("FIRE_YEAR_INT") != year
                        or props.get("OBJECTID") != row["object_id"]
                        or row["fire_year"] != year):
                    raise ValueError("stored government perimeter identity changed")
                _rings(geometry)
                canonical_feature = {"type": "Feature", "geometry": geometry,
                                     "properties": props}
                digest = hashlib.sha256(_canonical(canonical_feature).encode()).hexdigest()
                if digest != row["feature_sha256"]:
                    raise ValueError("stored government polygon SHA-256 mismatch")
                for k in attributes_present:
                    if props.get(k) is not None:
                        attributes_present[k] += 1
                polygons[geometry["type"]] += 1
                names.append(row["name"])
                if row["source_acres"] is not None:
                    acreages.append(float(row["source_acres"]))
                features.append({
                    **canonical_feature,
                    "id": f"nifc:{year}:{row['source_identity']}",
                })
            n_total = fetch["total_service_ids"]
            selected = fetch["selected_ids"]
            samples.append({
                "fire_year": year,
                "archive_status": "sampled_from_official_source",
                "batch_id": batch_id,
                "captured_at": fetch["captured_at"],
                "source_object_ids": n_total,
                "sampled_polygons": selected,
                "sample_fraction_of_published_ids": (
                    round(selected/n_total, 6) if n_total else None),
                "sample_selection_mode": fetch["selection_mode"],
                "sample_selection_seed": fetch["selection_seed"],
                "published_ids_sha256": fetch["ids_sha256"],
                "selected_ids_sha256": fetch["selected_ids_sha256"],
                "partial_source_record_sample": bool(fetch["subset_only"]),
                "source_census_complete": False,
                "evidence_availability": "retrospectively_collected_not_prospective",
                "geometry_types": polygons,
                "attributes_present_counts": attributes_present,
                "reported_acres_summary": {
                    "available": len(acreages),
                    "minimum": min(acreages) if acreages else None,
                    "median": statistics.median(acreages) if acreages else None,
                    "maximum": max(acreages) if acreages else None,
                    "units": "provider_reported_acres_not_computed_polygon_area",
                },
            })
    n = sum(r["sampled_polygons"] for r in samples)
    fully_captured = all(r["archive_status"] == "sampled_from_official_source"
                         for r in samples)
    study = {
        "schema_version": 1,
        "source_url": SERVICE,
        "rights_url": RIGHTS_URL,
        "source_description": "NIFC IFPH US retrospective polygon registry through 2019",
        "decision_at": decision,
        "requested_fire_years": list(year_ids),
        "year_results": samples,
        "stored_polygon_records": n,
        "complete_requested_year_sample": fully_captured,
        "source_fire_occurrence_coverage_complete": False,
        "negative_labels_created": 0,
        "model_ready": False,
        "research_evidence_kind": "retrospective_official_positive_perimeter_context",
        "warnings": [
            "This is an explicit sample of official published ObjectIDs; NOT all fires in a year.",
            "Seeded hashing randomizes ObjectID *selection order*, not geographic/time source coverage.",
            "A larger set of official source IDs does not prove more true wildfires occurred.",
            "Unrecorded or missing perimeters never support independent negative cases.",
            "A historical fire-year attribute is NOT when this information was available to a predictor.",
            "GIS_ACRES values are source attributes, not validated burned-area observations or model targets.",
        ],
    }
    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "provider": "NIFC Interagency Fire Perimeter History",
            "source_url": SERVICE, "rights_url": RIGHTS_URL,
            "as_of": decision,
            "fire_years": list(year_ids),
            "sample_only": True,
            "retrospective_not_prospective": True,
            "negative_labels_created": 0,
        },
    }
    return study, geojson


def run_study(db_path: str | Path, *, years: list[int],
              records_per_year: int = 12, seed: str = "wildfire-signals-v1",
              get_json=_fetch, clock=None) -> tuple[dict, dict]:
    """Bound live government retrieval by <=8 years, <=30 records per year.

    Each year is independently committed by sync_year. A later failure leaves
    earlier successful research captures intact; outputs are written only
    after the full requested study has completed.
    """
    year_ids = validate_years(years)
    if type(records_per_year) is not int or not 1 <= records_per_year <= MAX_STUDY_PER_YEAR:
        raise ValueError("records_per_year must be 1..30")
    if len(year_ids)*records_per_year > MAX_STUDY_POLYGONS:
        raise ValueError("study download budget exceeded")
    captured = _timestamp(clock() if clock else datetime.now(timezone.utc).isoformat())
    results = []
    for year in year_ids:
        outcome = sync_year(
            db_path, year=year, max_records=records_per_year,
            selection_mode="hash", selection_seed=seed, get_json=get_json,
            clock=lambda: captured)
        results.append(outcome)
    chosen = {r["fire_year"]: r["batch_id"] for r in results}
    report, geo = study_report(db_path, at=captured, years=list(year_ids),
                               required_batches=chosen)
    # Identify the batches from THIS run, even if a user already has other
    # research snapshots from other processes in the same archive.
    expected = {r["fire_year"]:r["batch_id"] for r in results}
    observed = {r["fire_year"]:r.get("batch_id") for r in report["year_results"]}
    if observed != expected:
        raise ValueError("study output is ambiguous: competing archive captures")
    report["study_run_batches"] = [r["batch_id"] for r in results]
    return report, geo


def _new_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (_canonical(data) + "\n").encode()
    if len(payload) > MAX_REPORT_FILE_BYTES:
        raise ValueError("study JSON export exceeds byte budget")
    with path.open("xb") as handle:
        handle.write(payload)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sample multiple real NIFC IFPH historical years; no negative labels")
    sub = parser.add_subparsers(dest="action", required=True)
    for command in ("sync", "report"):
        p = sub.add_parser(command, help="Fetch + report" if command == "sync"
                           else "Inspect local-only multi-year archive")
        p.add_argument("--db", type=Path, required=True)
        p.add_argument("--year", action="append", type=int, required=True)
        p.add_argument("--report", type=Path, required=True)
        p.add_argument("--geojson", type=Path)
        if command == "sync":
            p.add_argument("--records-per-year", type=int, default=12)
            p.add_argument("--seed", default="wildfire-signals-v1")
        else:
            p.add_argument("--at", required=True)
    args = parser.parse_args()
    targets = [args.report] + ([args.geojson] if args.geojson else [])
    if (len({p.resolve() for p in targets}) != len(targets)
            or any(p.resolve() == args.db.resolve() or p.exists() for p in targets)):
        parser.error("cannot overwrite source SQLite archive or existing output")
    if args.action == "sync":
        result, geo = run_study(args.db, years=args.year,
            records_per_year=args.records_per_year, seed=args.seed)
    else:
        result, geo = study_report(args.db, years=args.year, at=args.at)
    # Source has no all-or-none filesystem transaction across distinct output
    # paths. Preflight and exclusive-create keep normal repeated runs safe.
    _new_json(args.report, result)
    if args.geojson:
        _new_json(args.geojson, geo)
    print(json.dumps({
        "status": "sampled_official_source" if args.action == "sync" else "offline_archive",
        "years": result["requested_fire_years"],
        "polygons": result["stored_polygon_records"],
        "source_census_complete": False,
        "negative_labels_created": 0,
        "report": str(args.report),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
