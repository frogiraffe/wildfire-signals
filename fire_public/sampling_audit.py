"""Offline source-denominator and label-review attrition audit.

This is a study flow report, not an incidence estimate. It keeps the official
perimeter record denominator separate from the independent frame denominator.
"""
from __future__ import annotations

import argparse
import html
import json
from collections import Counter, defaultdict
from pathlib import Path

from .label_review import (
    MAX_FRAME_BYTES, MAX_REVIEW_BYTES, _load, _review_decision, _sha, _text,
    _write_new,
)
from .labeled_evaluation import _manifest
from .review_intake import _queue


def _count(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"nonnegative {name} count required")
    return value


def _region_counts(value: object, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} region counts required")
    result = {}
    for region, count in value.items():
        key = _text(region, "frame region")
        if key in result:
            raise ValueError("duplicate frame region")
        result[key] = _count(count, label)
    return result


def build_audit(queue_path: Path, reviews_path: Path | None = None,
                protocol_path: Path | None = None) -> dict:
    """Check queue count contracts and optionally validate every review decision."""
    q, cases, digest = _queue(queue_path)
    official = [case for case in cases.values() if
                case["kind"] == "retrospective_official_perimeter_review"]
    frame_cases = [case for case in cases.values() if
                   case["kind"] == "independent_frame_review"]
    batches = q.get("source_batches")
    if not isinstance(batches, list) or not batches:
        raise ValueError("official source batch denominators required")
    source_rows = []
    years = set()
    for item in batches:
        if not isinstance(item, dict):
            raise ValueError("official source batch must be an object")
        year = item.get("fire_year")
        if type(year) is not int or year in years:
            raise ValueError("distinct official source years required")
        years.add(year)
        archived = _count(item.get("archived_polygon_count"), "archived polygon")
        published = _count(item.get("source_record_count"), "published source ID")
        if archived > published or not item.get("batch_id"):
            raise ValueError("official source batch count or identity invalid")
        source_rows.append({"fire_year": year, "batch_id": item["batch_id"],
                            "published_source_ids": published,
                            "archived_leads": archived,
                            "source_id_sample_fraction": archived / published if published else None})
    if sum(item["archived_leads"] for item in source_rows) != len(official):
        raise ValueError("official source batch counts disagree with queue")
    source_rows.sort(key=lambda row: row["fire_year"])
    frame = q.get("sampling_frame")
    if not isinstance(frame, dict):
        raise ValueError("independent sampling frame metadata required")
    population = _region_counts(frame.get("population_by_region"), "population")
    selected = _region_counts(frame.get("selected_by_region"), "selected")
    observed = Counter(case.get("region_id") for case in frame_cases)
    if (selected != dict(observed) or
            sum(population.values()) != _count(frame.get("population_units"), "frame population") or
            sum(selected.values()) != _count(frame.get("sampled_units"), "selected frame") or
            set(selected) - set(population) or
            any(n > population[region] for region, n in selected.items())):
        raise ValueError("selected frame counts disagree with queue or population")
    frame_rows = [{"region_id": region, "population_units": n,
                   "selected_units": selected.get(region, 0),
                   "selection_fraction": selected.get(region, 0) / n if n else None}
                  for region, n in sorted(population.items())]
    result = {
        "schema_version": 1, "queue_sha256": digest,
        "frame_name": frame.get("name"),
        "frame_input_sha256": frame.get("input_sha256"),
        "frame_selection_strategy": frame.get("selection_strategy"),
        "official_sources": source_rows, "frame_regions": frame_rows,
        "queued_official_leads": len(official), "queued_frame_units": len(frame_cases),
        "review_attrition": None, "by_source_kind": None, "by_frame_region": None,
        "population_prevalence_identifiable": False,
        "sampling_interpretation": (
            "Official published perimeter IDs and externally enumerated frame units are "
            "different denominators. Seeded region balancing and review exclusions do not "
            "give population inclusion probabilities. No population wildfire prevalence, "
            "calibration or detection accuracy follows from these counts."),
    }
    if reviews_path is None:
        if protocol_path is not None:
            raise ValueError("protocol requires reviews")
        return result
    if protocol_path is None:
        raise ValueError("protocol required to validate review chronology and horizon")
    reviews = _load(reviews_path, MAX_REVIEW_BYTES)
    if reviews.get("queue_sha256") != digest:
        raise ValueError("review decisions queue SHA does not match source queue")
    entries = reviews.get("decisions")
    if not isinstance(entries, list) or len(entries) != len(cases):
        raise ValueError("reviews must address every queued case")
    by_review = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("review decision must be an object")
        case_id = _text(entry.get("case_id"), "review case identity")
        if case_id in by_review:
            raise ValueError("duplicate review decision")
        by_review[case_id] = entry
    if set(by_review) != set(cases):
        raise ValueError("reviews must address every queued case")
    protocol = _load(protocol_path, MAX_FRAME_BYTES)
    _manifest(protocol)
    horizon = float(protocol["horizon_hours"])
    attrition = Counter()
    by_kind: dict[str, Counter] = defaultdict(Counter)
    by_region: dict[str, Counter] = defaultdict(Counter)
    for case_id, case in cases.items():
        entry = by_review[case_id]
        row = _review_decision(case, entry, horizon)
        status = entry["status"]
        key = f"adjudicated_{'positive' if row['label'] else 'negative'}" if row else status
        attrition[key] += 1
        by_kind[case["kind"]][key] += 1
        if case["kind"] == "independent_frame_review":
            by_region[case["region_id"]][key] += 1
    result.update({
        "reviews_sha256": _sha(reviews_path), "protocol_sha256": _sha(protocol_path),
        "review_attrition": {key: attrition[key] for key in
                             ("adjudicated_positive", "adjudicated_negative",
                              "unresolved", "excluded")},
        "by_source_kind": {kind: dict(sorted(counts.items())) for kind, counts in
                           sorted(by_kind.items())},
        "by_frame_region": {region: dict(sorted(counts.items())) for region, counts in
                            sorted(by_region.items())},
    })
    return result


def render_html(audit: dict) -> str:
    """Read-only escaped study-flow report suitable for private local viewing."""
    e = lambda value: html.escape(str(value), quote=True)
    def table(headers: list[str], rows: list[list[object]]) -> str:
        head = "".join(f"<th scope=\"col\">{e(value)}</th>" for value in headers)
        body = "".join("<tr>"+"".join(f"<td>{e(value)}</td>" for value in row)+"</tr>"
                       for row in rows)
        return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    sources = table(["Fire year", "Published IDs", "Archived leads", "ID sample fraction"],
                    [[item["fire_year"],item["published_source_ids"],
                      item["archived_leads"],item["source_id_sample_fraction"]]
                     for item in audit["official_sources"]])
    regions = table(["Frame region", "Enumerated units", "Selected units", "Selection fraction"],
                    [[item["region_id"],item["population_units"],
                      item["selected_units"],item["selection_fraction"]]
                     for item in audit["frame_regions"]])
    review = "<p>No review decisions supplied; all cases remain unlabeled here.</p>"
    if audit["review_attrition"] is not None:
        review = table(["Review outcome", "Cases"],
                       [[key, value] for key, value in audit["review_attrition"].items()])
    return ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Wildfire review sampling audit</title>"
            "<style>body{font:1rem/1.5 system-ui;max-width:60rem;margin:2rem auto;padding:0 1rem}"
            "table{border-collapse:collapse;width:100%;margin-bottom:2rem}td,th{border:1px solid #aaa;padding:.4rem;text-align:left}"
            "table{display:block;overflow-x:auto}</style>"
            f"<h1>Sampling and review audit</h1><p>Frame: {e(audit['frame_name'])}</p>"
            f"<p>{e(audit['sampling_interpretation'])}</p>"
            "<h2>Official source record sample</h2>" + sources +
            "<h2>Independent frame selection</h2>" + regions +
            "<h2>Review attrition</h2>" + review + "</html>\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Private label review sampling and attrition audit")
    parser.add_argument("--queue", required=True, type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--html", required=True, type=Path)
    args = parser.parse_args()
    outputs = [args.json, args.html]
    inputs = [p for p in (args.queue, args.reviews, args.protocol) if p is not None]
    if (len({p.resolve() for p in outputs}) != len(outputs) or
            any(p.resolve() in {x.resolve() for x in inputs} or p.exists()
                for p in outputs)):
        parser.error("outputs must be new, distinct, and cannot overwrite inputs")
    audit = build_audit(args.queue, args.reviews, args.protocol)
    created = []
    try:
        for path, content in ((args.json, json.dumps(audit, indent=2, ensure_ascii=False)+"\n"),
                              (args.html, render_html(audit))):
            _write_new(path, content)
            created.append(path)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    print(json.dumps({"json":str(args.json),"html":str(args.html),
                      "population_prevalence_identifiable":False},sort_keys=True))


if __name__ == "__main__":
    main()
