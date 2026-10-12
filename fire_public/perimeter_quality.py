"""Source-backed, fail-closed quality assessment of NIFC sampled fire perimeters.

All statistics describe archived *sampled provider records*, never all US
wildfires, wildfire absence, burned-area progression or forecast accuracy.
Reads existing SHA-256-verified, versioned SQLite via perimeter_study.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from .official_perimeters import _canonical, _rings
from .perimeter_study import study_report, validate_years

FIELDS = ("OBJECTID", "GlobalID", "FIRE_YEAR_INT", "INCIDENT",
          "GIS_ACRES", "SOURCE")
CRITICAL = ("OBJECTID", "FIRE_YEAR_INT", "GlobalID")
MAX_FLAGS = 240
MISSING = (None, "")


def _usable(value) -> bool:
    return (value is not None and
            (not isinstance(value, str) or bool(value.strip())))


def _lon_span(points: list[float]) -> tuple[float, bool]:
    # Smallest covering longitude arc, not a country extent or exact polygon
    # width. Longitude-wrap ambiguity is reported explicitly.
    lon = sorted(set(((float(v) + 360.0) % 360.0) for v in points))
    if len(lon) < 2:
        return 0.0, False
    gaps = [lon[i+1] - lon[i] for i in range(len(lon)-1)]
    gaps.append(lon[0] + 360.0 - lon[-1])
    width = 360.0 - max(gaps)
    return round(width, 6), max(points) - min(points) > 180


def _ring_degenerate(ring: list[list[float]]) -> bool:
    """Planar *degeneracy* screen only; NOT a topology or acreage validator."""
    if len({(p[0], p[1]) for p in ring[:-1]}) < 3:
        return True
    unwrapped = [float(ring[0][0])]
    for point in ring[1:]:
        previous = unwrapped[-1]
        step = ((float(point[0]) - previous + 180) % 360) - 180
        unwrapped.append(previous + step)
    twice_area = sum(
        unwrapped[i] * float(ring[i+1][1]) -
        unwrapped[i+1] * float(ring[i][1])
        for i in range(len(ring)-1))
    return abs(twice_area) < 1e-12


def _record(feature: dict, *, year: int) -> dict:
    props = feature["properties"]
    geometry = feature["geometry"]
    rings = _rings(geometry)
    points = [p for ring in rings for p in ring]
    if props["FIRE_YEAR_INT"] != year:
        raise ValueError("cross-year source feature contamination")
    lon_width, dateline = _lon_span([p[0] for p in points])
    gis_acres = props.get("GIS_ACRES")
    flags = []
    if not _usable(props.get("GlobalID")):
        flags.append("missing_source_global_id")
    if not _usable(props.get("INCIDENT")):
        flags.append("missing_incident_name")
    if not _usable(props.get("SOURCE")):
        flags.append("missing_optional_source_agency_field")
    if gis_acres is None or gis_acres == "":
        flags.append("missing_reported_acres")
    elif type(gis_acres) not in (int, float) or not math.isfinite(gis_acres):
        flags.append("invalid_reported_acres")
    elif gis_acres <= 0:
        flags.append("nonpositive_reported_acres")
    if any(_ring_degenerate(r) for r in rings):
        flags.append("degenerate_coordinate_ring")
    # Treat very wide shapes as a manual inspection signal, never truncate.
    if lon_width > 120:
        flags.append("extreme_longitude_span_review")
    if dateline:
        flags.append("longitude_wrap_requires_review")
    digest = hashlib.sha256(_canonical(geometry).encode()).hexdigest()
    return {
        "source_object_id": props["OBJECTID"],
        "source_global_id": str(props.get("GlobalID") or ""),
        "geometry_sha256": digest,
        "name": str(props.get("INCIDENT") or ""),
        "reported_acres": gis_acres,
        "ring_count": len(rings),
        "vertices": sum(len(r) for r in rings),
        "longitude_arc_degrees": lon_width,
        "latitude_range_degrees": [
            round(min(p[1] for p in points), 6),
            round(max(p[1] for p in points), 6),
        ],
        "flags": sorted(set(flags)),
    }


def audit_quality(db: str | Path, *, at: str, years: list[int],
                  required_batches: dict[int, str] | None = None) -> dict:
    """Recalculate all file and batch checksums before a descriptive audit."""
    year_ids = validate_years(years)
    baseline, geo = study_report(db, at=at, years=list(year_ids),
                                 required_batches=required_batches)
    by_year = defaultdict(list)
    for feature in geo["features"]:
        by_year[feature["properties"]["FIRE_YEAR_INT"]].append(feature)
    annual = []
    flags = []
    all_geometry = defaultdict(list)
    for year_row in baseline["year_results"]:
        year = year_row["fire_year"]
        features = by_year[year]
        if len(features) != year_row["sampled_polygons"]:
            raise ValueError("archive year sample and GeoJSON disagree")
        count = len(features)
        field_present = {k: 0 for k in FIELDS}
        field_population = Counter()
        usable_acres = []
        risk_count = Counter()
        vertices = []
        affected = 0
        for f in features:
            props = f["properties"]
            for key, value in props.items():
                if _usable(value):
                    field_population[key] += 1
            for key in FIELDS:
                field_present[key] += int(_usable(props.get(key)))
            value = _record(f, year=year)
            vertices.append(value["vertices"])
            acres = value["reported_acres"]
            if type(acres) in (float, int) and math.isfinite(acres) and acres > 0:
                usable_acres.append(float(acres))
            for code in value["flags"]:
                risk_count[code] += 1
            if value["flags"]:
                affected += 1
                if len(flags) >= MAX_FLAGS:
                    raise ValueError("quality issue audit exceeds row budget")
                flags.append({
                    "fire_year": year,
                    "source_object_id": value["source_object_id"],
                    "source_global_id": value["source_global_id"],
                    "name": value["name"],
                    "flags": value["flags"],
                })
            all_geometry[value["geometry_sha256"]].append({
                "fire_year": year, "source_object_id": value["source_object_id"],
                "source_global_id": value["source_global_id"],
            })
        annual.append({
            "fire_year": year,
            "archive_status": year_row["archive_status"],
            "archived_batch_id": year_row.get("batch_id"),
            "archive_captured_at": year_row.get("captured_at"),
            "published_source_id_count": year_row["source_object_ids"],
            "sampled_record_count": count,
            "selection_fraction_of_source_ids":
                year_row["sample_fraction_of_published_ids"],
            "sample_mode": year_row.get("sample_selection_mode"),
            "selection_seed": year_row.get("sample_selection_seed"),
            "source_census_complete": False,
            "sample_flagged_records": affected,
            "flags_by_type": dict(sorted(risk_count.items())),
            "field_presence": {
                key: {
                    "nonempty_sampled_records": field_present[key],
                    "sampled_denominator": count,
                    "sample_fraction": round(field_present[key]/count, 4)
                        if count else None,
                }
                for key in FIELDS
            },
            "all_fields_present_in_sample": dict(sorted(field_population.items())),
            "positive_reported_acres_count": len(usable_acres),
            "source_reported_acres_median":
                statistics.median(usable_acres) if usable_acres else None,
            "vertex_count_median":
                statistics.median(vertices) if vertices else None,
            "sampling_not_a_complete_incidence_frame": True,
        })
    duplicated = [{
        "geometry_sha256": digest,
        "distinct_source_records": len(refs),
        "records": refs,
        "note": "Exact matching polygon bytes; may be intentional/duplicate version or event. Manual review required.",
    } for digest, refs in sorted(all_geometry.items())
      if len(refs) > 1]
    # A fully downloaded *source-ID list* can be incomplete relative to actual
    # wildfires; even clean sampled attributes cannot prove negative coverage.
    observed = sum(r["sampled_record_count"] for r in annual)
    unavailable = [r["fire_year"] for r in annual
                   if r["archive_status"] != "sampled_from_official_source"]
    return {
        "schema_version": 1,
        "research_status": "descriptive_sampled_official_perimeter_quality",
        "source": baseline["source_url"],
        "rights": baseline["rights_url"],
        "as_of": baseline["decision_at"],
        "study_years": list(year_ids),
        "year_quality": annual,
        "sampled_polygons_total": observed,
        "uncaptured_years": unavailable,
        "flagged_source_records": flags,
        "exact_duplicate_polygon_groups": duplicated,
        "sample_flagged_count": sum(r["sample_flagged_records"] for r in annual),
        "source_coverage_status": "not_a_verified_complete_fire_census",
        "negative_sampling_readiness": {
            "independent_positive_context_exists": observed > 0,
            "independently_verified_nonfire_frame": False,
            "full_temporal_reporting_coverage": False,
            "national_fire_occurrence_denominator_verified": False,
            "forecast_input_issue_time_audited": False,
            "training_ready": False,
            "required_next_evidence": [
                "Versioned independent outcome adjudication, not just polygon appearance",
                "A documented region-time sampling frame and independent non-fire checks",
                "Agency reporting scope, inclusion rules and observation/censoring windows",
                "Weather/remote-sensing feature issue and availability timestamps",
                "Chronological and geographical split with embargo and source audit",
            ],
        },
        "negative_labels_created": 0,
        "forecast_skill_measured": False,
        "warnings": [
            "Field fractions are computed ONLY over downloaded sampled source polygons; no national inference.",
            "A blank SOURCE/INCIDENT/GIS_ACRES field is a quality flag, not proof the polygon is invalid.",
            "Geometry screens check obvious degenerate rings and longitude-wrap; they are not topology validation.",
            "GIS_ACRES is an unverified provider attribute; geometry coordinates are not ground-truth acres.",
            "An uncaptured year has unknown observations, NOT zero government fires.",
            "Matched geometry hashes across years are review candidates, not automatically deduplicated events.",
            "Never turn absence of official historical fire perimeters into binary no-fire labels.",
        ],
    }


def render_quality_html(audit: dict) -> str:
    """Portable, escaped, no-JS source-quality report for review."""
    esc = lambda s: html.escape(str(s), quote=True)
    rows = []
    for year in audit["year_quality"]:
        if year["sampled_record_count"]:
            rates = " · ".join(
                f"{key} {int(100*value['sample_fraction'])}%"
                for key, value in year["field_presence"].items()
                if value["sample_fraction"] is not None)
        else:
            rates = "No capture: unknown source field coverage"
        rows.append("<tr><td>" + esc(year["fire_year"]) +
            "</td><td>" + esc(year["archive_status"]) +
            "</td><td>" + esc(year["published_source_id_count"]) +
            "</td><td>" + esc(year["sampled_record_count"]) +
            "</td><td>" + esc(year["sample_flagged_records"]) +
            "</td><td>" + esc(rates) + "</td></tr>")
    issues = "".join(
        "<li>" + esc(row["fire_year"]) + " / " +
        esc(row["source_object_id"]) + " — " +
        esc(row["name"]) + " — " +
        esc(", ".join(row["flags"])) + "</li>"
        for row in audit["flagged_source_records"])
    duplicated = "".join(
        "<li>" + esc(r["geometry_sha256"][:16]) + " — " +
        esc(r["distinct_source_records"]) + " distinct source IDs</li>"
        for r in audit["exact_duplicate_polygon_groups"])
    warnings = "".join("<p>" + esc(msg) + "</p>" for msg in audit["warnings"])
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wildfire Signals — NIFC sampled source quality</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif;background:#132632;color:#eef7f9}
body{margin:auto;max-width:1160px;padding:22px;line-height:1.55}
section{padding:16px;border:1px solid #4e717e;border-radius:12px;margin:12px 0}
table{width:100%;border-collapse:collapse}th,td{border-bottom:1px solid #4b6b78;
text-align:left;padding:9px;vertical-align:top;overflow-wrap:anywhere}
small,.quiet{color:#c8dce0}th{color:#c5e3e6}h1{font-size:1.7rem}h2{font-size:1.15rem}
.warning{color:#f3c58a}ul{overflow-wrap:anywhere}
@media(max-width:640px){body{padding:9px}table{display:block;overflow-x:auto;font-size:.8rem}}
</style></head><body><h1>NIFC official source sample quality</h1>
<p class="warning">Descriptive quality of sampled historical agency polygons;
not nationwide wildfire occurrence, absence or forecast accuracy.</p>""" +
        "<p>As of " + esc(audit["as_of"]) + " · polygon records " +
        esc(audit["sampled_polygons_total"]) + "</p>" +
        "<section><h2>Year-by-year evidence</h2><table><thead><tr>" +
        "<th>Fire year</th><th>Archive status</th><th>Published source IDs</th>" +
        "<th>Sampled</th><th>Flagged</th><th>Field completeness in sample</th>" +
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></section>" +
        "<section><h2>Sample record review queue</h2><ul>" + issues +
        "</ul><h2>Duplicate exact geometries</h2><ul>" + duplicated +
        "</ul></section><section><h2>Scientific limits</h2>" + warnings +
        "<p>Independent negative sampling ready: <strong>No</strong>.</p>" +
        "</section></body></html>")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit real-sourced historical perimeter sample, never fire negatives")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--year", action="append", type=int, required=True)
    parser.add_argument("--at", required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--html", type=Path)
    args = parser.parse_args()
    paths = [args.json] + ([args.html] if args.html else [])
    if (len(set(p.resolve() for p in paths)) != len(paths)
            or any(p.resolve() == args.db.resolve() or p.exists() for p in paths)):
        parser.error("reports cannot overwrite source SQLite or existing files")
    output = audit_quality(args.db, at=args.at, years=args.year)
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (json.dumps(output, ensure_ascii=False, indent=2,
                              sort_keys=True, allow_nan=False) + "\n"
                   if path == args.json else render_quality_html(output))
        with path.open("x", encoding="utf-8") as stream:
            stream.write(content)
    print(json.dumps({
        "source_samples": output["sampled_polygons_total"],
        "flagged_samples": output["sample_flagged_count"],
        "years": output["study_years"],
        "negative_labels_created": output["negative_labels_created"],
        "source_coverage_complete": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
