"""Auditable review queue between real perimeter evidence and binary evaluation.

Historic government perimeters give review leads only: not prospective
features, dates of ignition, confirmed targets or valid non-fire controls.
A user-supplied independently enumerated region/time sampling frame gives
*unknown* controls. No label exists until two identified reviewers adjudicate
with explicit independent evidence and negative coverage verification.

This is deliberately an offline, opt-in private research tool, not a public
wildfire accuracy service or a machine-created source of ground truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from .history import _timestamp
from .labeled_evaluation import _audit_rows, _manifest
from .official_perimeters import SERVICE
from .perimeter_study import study_report, validate_years

MAX_FRAME_BYTES = 2_000_000
MAX_REVIEW_BYTES = 8_000_000
MAX_CASES = 400
MAX_SOURCE_CANDIDATES = 240


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path, cap: int) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > cap:
        raise ValueError(f"missing or oversized research input: {path}")
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("research input must be a JSON object")
    return obj


def _url(value: object) -> bool:
    return isinstance(value, str) and value.startswith("https://") and len(value) <= 2048


def _text(value: object, label: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= 500:
        raise ValueError(f"meaningful {label} required")
    return value.strip()


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(_timestamp(value))


def _valid_point(item: dict) -> None:
    for name, lo, hi in (("latitude", -90, 90), ("longitude", -180, 180)):
        x = item.get(name)
        if type(x) not in (int, float) or not math.isfinite(x) or not lo <= x <= hi:
            raise ValueError(f"frame must have valid WGS84 {name}")


def prepare_queue(perimeter_db: Path, *, at: str, years: list[int],
                  frame_path: Path, seed: str = "wildfire-review-v1",
                  max_controls: int = 80) -> dict:
    """Use real provenance-checked source IDs and an external frame, never pseudo-label."""
    validate_years(years)
    _text(seed, "stable sampling seed")
    if type(max_controls) is not int or not 1 <= max_controls <= 200:
        raise ValueError("max_controls must be 1..200")
    frame = _load(frame_path, MAX_FRAME_BYTES)
    if frame.get("schema_version") != 1:
        raise ValueError("frame schema_version 1 required")
    for key in ("frame_name", "sampling_protocol", "frame_provenance"):
        _text(frame.get(key), key, 8)
    if not _url(frame.get("source_url")) or not _url(frame.get("rights_url")):
        raise ValueError("independent sampling frame source and rights URLs required")
    slots = frame.get("units")
    if not isinstance(slots, list) or not 1 <= len(slots) <= MAX_CASES:
        raise ValueError("frame needs 1..400 independently enumerated region-time units")
    by_id = {}
    seen_locations = set()
    queue_as_of = _utc(at)
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("frame unit must be an object")
        identity = _text(slot.get("sampling_unit_id"), "frame sampling identity")
        _text(slot.get("region_id"), "frame region")
        _valid_point(slot)
        decision_at = _utc(slot.get("decision_at"))
        if decision_at > queue_as_of:
            raise ValueError("frame decision after queue as-of cutoff")
        location = (slot["region_id"], slot["latitude"], slot["longitude"], decision_at)
        if location in seen_locations:
            raise ValueError("duplicate region-time location in independent frame")
        seen_locations.add(location)
        if identity in by_id:
            raise ValueError("duplicate independent frame sampling identity")
        by_id[identity] = slot
    original, geo = study_report(perimeter_db, at=at, years=years)
    if not original["complete_requested_year_sample"]:
        raise ValueError("all requested official years need archived source batches by queue as-of")
    cases = []
    for feature in geo["features"]:
        props = feature["properties"]
        year = props["FIRE_YEAR_INT"]
        oid = props["OBJECTID"]
        key = f"official:{year}:{oid}"
        cases.append({
            "case_id": key, "kind": "retrospective_official_perimeter_review",
            "proposed_label": None, "review_status": "unresolved",
            "source": SERVICE,
            "source_fire_year": year, "source_object_id": oid,
            "source_global_id": props.get("GlobalID"),
            "source_name": props.get("INCIDENT"),
            "location_status": "requires_independent_region_and_event_date",
            "evidence_role": "retrospective_positive_context_only",
        })
    if len(cases) > MAX_SOURCE_CANDIDATES:
        raise ValueError("bounded source candidate limit exceeded")
    # Balanced region-id round robin avoids selecting all controls from a
    # high-volume stratum when frame sizes differ. Still NOT representative:
    # it depends entirely on the supplied independent sampling frame.
    groups: dict[str, list[str]] = {}
    for identity, item in by_id.items():
        groups.setdefault(item["region_id"], []).append(identity)
    for region, identities in groups.items():
        identities.sort(key=lambda identity: (
            hashlib.sha256(f"{seed}:{region}:{identity}".encode()).digest(),identity))
    ordered_regions = sorted(groups, key=lambda region: (
        hashlib.sha256(f"{seed}:region:{region}".encode()).digest(), region))
    chosen = []
    while len(chosen) < max_controls:
        any_available = False
        for region in ordered_regions:
            if groups[region]:
                any_available = True
                chosen.append(groups[region].pop(0))
                if len(chosen) >= max_controls:
                    break
        if not any_available:
            break
    for identity in sorted(chosen):
        item = by_id[identity]
        cases.append({
            "case_id": f"frame:{identity}", "kind": "independent_frame_review",
            "proposed_label": None, "review_status": "unresolved",
            "sampling_unit_id": identity,
            "region_id": item["region_id"],
            "latitude": item["latitude"], "longitude": item["longitude"],
            "decision_at": _timestamp(item["decision_at"]),
            "evidence_role": "unlabeled_region_time_sample",
        })
    if len(cases) > MAX_CASES:
        raise ValueError("total research review queue exceeds 400 cases")
    return {
        "schema_version": 1, "state": "unadjudicated_review_queue",
        "as_of": original["decision_at"],
        "official_source": original["source_url"],
        "source_batches": [
            {"fire_year": x["fire_year"], "batch_id": x.get("batch_id"),
             "archived_polygon_count": x["sampled_polygons"],
             "source_record_count": x["source_object_ids"]}
            for x in original["year_results"]],
        "sampling_frame": {
            "name": frame["frame_name"], "source": frame["source_url"],
            "rights": frame["rights_url"], "protocol": frame["sampling_protocol"],
            "provenance": frame["frame_provenance"],
            "input_sha256": _sha(frame_path),
            "population_units": len(slots), "sampled_units": len(chosen),
            "selection_strategy": "seeded_hash_region_round_robin",
            "population_by_region": dict(sorted(Counter(
                item["region_id"] for item in by_id.values()).items())),
            "selected_by_region": dict(sorted(Counter(
                by_id[identity]["region_id"] for identity in chosen).items())),
            "seed": seed,
        },
        "cases": cases,
        "counts": {
            "official_perimeter_leads": len(geo["features"]),
            "unlabeled_frame_units": len(chosen),
            "adjudicated_positive": 0, "adjudicated_negative": 0,
        },
        "not_ground_truth": True, "negative_labels_created": 0,
        "warnings": [
            "Historical NIFC perimeter FIRE_YEAR is not event date or historical feature availability.",
            "No region-time frame slot is presumed fire-free; all cases start unresolved.",
            "The frame is independently supplied; its representativeness and completeness require review.",
            "Do not use a perimeter lead as an independent negative case.",
            "Adjudication requires two distinct reviewers and independent incident or nonfire evidence.",
        ],
    }


def _review_decision(case: dict, entry: dict, horizon: float) -> dict | None:
    status = entry.get("status")
    if status in ("excluded", "unresolved"):
        _text(entry.get("reason"), "nonadjudicated reason", 8)
        return None
    if status != "adjudicated":
        raise ValueError("each case must be adjudicated, excluded, or unresolved")
    label = entry.get("label")
    if type(label) is not int or label not in (0, 1):
        raise ValueError("adjudicated binary label must be 0 or 1")
    if label == 0 and case["kind"] == "retrospective_official_perimeter_review":
        raise ValueError("NIFC positive evidence may not be converted into fire absence")
    primary, secondary = entry.get("primary"), entry.get("secondary")
    if not isinstance(primary, dict) or not isinstance(secondary, dict):
        raise ValueError("two independent reviewer records required")
    primary_id = _text(primary.get("reviewer_id"), "primary reviewer")
    secondary_id = _text(secondary.get("reviewer_id"), "secondary reviewer")
    if primary_id == secondary_id:
        raise ValueError("two distinct human reviewers required")
    for reviewer in (primary, secondary):
        if (reviewer.get("agrees_with_label") is not True
                or type(reviewer.get("reviewer_label")) is not int
                or reviewer["reviewer_label"] != label
                or reviewer.get("independent_evidence_checked") is not True
                or not _url(reviewer.get("evidence_url"))):
            raise ValueError("both reviewers must independently vote for label and cite evidence")
    timestamp = _utc(_text(entry.get("decision_at"), "prediction decision time"))
    feature_at = _utc(_text(entry.get("feature_cutoff_at"), "feature issue-time cutoff"))
    available = _utc(_text(entry.get("label_available_at"), "source label availability"))
    verified = _utc(_text(entry.get("label_verified_at"), "label review timestamp"))
    p_time, s_time = [_utc(_text(x.get("reviewed_at"), "reviewer timestamp"))
                      for x in (primary, secondary)]
    if (feature_at > timestamp or available <= timestamp
            or verified < max(available, p_time, s_time)
            or min(p_time, s_time) < available):
        raise ValueError("invalid as-of feature, source publication or adjudication chronology")
    window_end = timestamp + timedelta(hours=horizon)
    if case["kind"] == "independent_frame_review":
        if (_timestamp(entry["decision_at"]) != case["decision_at"]
                or entry.get("region_id") != case["region_id"]):
            raise ValueError("frame case cannot change predefined region or decision")
    if label == 1:
        occurrence = _utc(_text(entry.get("independently_verified_event_at"),
                                "independent occurrence timestamp"))
        if not timestamp <= occurrence <= window_end:
            raise ValueError("verified positive event outside declared prediction horizon")
        if (case["kind"] == "retrospective_official_perimeter_review"
                and occurrence.year != case["source_fire_year"]):
            raise ValueError("official perimeter fire year conflicts with verified event")
    else:
        coverage = entry.get("negative_coverage")
        if not isinstance(coverage, dict):
            raise ValueError("negative label needs independent whole-window coverage")
        if not _url(coverage.get("completeness_evidence_url")):
            raise ValueError("negative registry coverage evidence URL required")
        if coverage.get("registry_complete_for_unit_window") is not True:
            raise ValueError("coverage cannot be inferred from missing fires")
        start = _utc(_text(coverage.get("start_at"), "coverage start"))
        end = _utc(_text(coverage.get("end_at"), "coverage end"))
        if start > timestamp or end < window_end:
            raise ValueError("negative coverage must include entire declared horizon")
        reviewer = _text(coverage.get("coverage_reviewer_id"), "negative coverage reviewer")
        if reviewer in (primary_id, secondary_id):
            raise ValueError("negative coverage requires independent third reviewer")
        coverage_reviewed = _utc(_text(coverage.get("reviewed_at"), "coverage audit timestamp"))
        if coverage_reviewed < max(end, available):
            raise ValueError("negative coverage must be verified after observation window")
        if verified < coverage_reviewed:
            raise ValueError("final label verification must occur after third coverage review")
    source = _text(entry.get("label_source"), "independent source")
    if source.casefold() in ("firms", "satellite_candidate", "thermal_detection"):
        raise ValueError("FIRMS thermal detections are not independent wildfire ground truth")
    if not _url(entry.get("label_evidence_url")):
        raise ValueError("independently reviewed label evidence URL required")
    _text(entry.get("label_source_id"), "source record identity")
    event = _text(entry.get("event_id"), "verified incident or sampling event identity")
    region = _text(entry.get("region_id"), "independently assigned study region")
    return {
        "event_id": event, "region_id": region,
        "decision_at": timestamp.isoformat(),
        "feature_cutoff_at": feature_at.isoformat(),
        "label_available_at": available.isoformat(),
        "label_verified_at": verified.isoformat(),
        "label": label, "label_source": source,
        "label_source_id": entry["label_source_id"],
        "label_evidence_url": entry["label_evidence_url"],
        "case_sampling_id": case["case_id"],
    }


def finalize_queue(queue_path: Path, reviews_path: Path,
                   protocol_path: Path) -> tuple[list[dict], dict, dict]:
    """Reject unsafe shortcuts; preserve unresolved/excluded counts and provenance."""
    q = _load(queue_path, MAX_REVIEW_BYTES)
    reviews = _load(reviews_path, MAX_REVIEW_BYTES)
    p = _load(protocol_path, MAX_FRAME_BYTES)
    if q.get("state") != "unadjudicated_review_queue" or q.get("schema_version") != 1:
        raise ValueError("proper unadjudicated source queue required")
    cases = q.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("review queue empty or too large")
    by_id = {row["case_id"]: row for row in cases}
    if len(by_id) != len(cases):
        raise ValueError("duplicated case identities in original queue")
    entries = reviews.get("decisions")
    if not isinstance(entries, list) or len(entries) != len(cases):
        raise ValueError("every queued case needs an explicit reviewed/unresolved/excluded decision")
    decisions = {row["case_id"]: row for row in entries}
    if len(decisions) != len(entries) or set(decisions) != set(by_id):
        raise ValueError("decision identities must exactly equal queued case identities")
    if reviews.get("queue_sha256") != _sha(queue_path):
        raise ValueError("review decisions do not match immutable source queue digest")
    if p.get("schema_version") != 1:
        raise ValueError("audited cohort protocol manifest schema_version 1 required")
    # Never infer attestations. They are explicit human statements and need a
    # named author, reviewed dates and a specific independent coverage source.
    if not p.get("negative_coverage_audited") is True or not p.get(
            "independent_label_provenance_verified") is True:
        raise ValueError("independent label and negative coverage attestations required")
    _text(p.get("coverage_attested_by"), "coverage attestor", 8)
    _utc(_text(p.get("coverage_attested_at"), "coverage attestation timestamp"))
    if not _url(p.get("coverage_evidence_url")):
        raise ValueError("independent full sampling coverage source required")
    _manifest(p)
    horizon = float(p["horizon_hours"])
    rows, counts = [], Counter()
    for case in cases:
        decision = decisions[case["case_id"]]
        row = _review_decision(case, decision, horizon)
        counts[decision["status"]] += 1
        if row is not None:
            rows.append(row)
            counts[f"label_{row['label']}"] += 1
    if not rows:
        raise ValueError("no independently reviewed outcomes for cohort")
    _audit_rows(rows, p)
    if not counts["label_0"] or not counts["label_1"]:
        raise ValueError("positive and independently audited negative examples both required")
    if _utc(p["coverage_attested_at"]) < max(
            _utc(row["label_verified_at"]) for row in rows):
        raise ValueError("coverage attestation must postdate adjudicated outcomes")
    manifest = dict(p)
    manifest.update({
        "review_queue_sha256": _sha(queue_path),
        "review_decisions_sha256": _sha(reviews_path),
        "sampling_frame_sha256": q["sampling_frame"]["input_sha256"],
        "cohort_origin": "double_reviewed_provided_external_evidence",
        "evidence_claim_type": "human_attested_not_independently_verified_by_software",
        "review_counts": dict(sorted(counts.items())),
        "scientific_caveat": (
            "Evidence URLs, source completeness and human review attestations "
            "are structurally checked, not externally validated by this program."),
    })
    result = {
        "schema_version": 1, "queue_sha256": _sha(queue_path),
        "reviews_sha256": _sha(reviews_path),
        "protocol_sha256": _sha(protocol_path),
        "adjudicated_rows": len(rows), "excluded": counts["excluded"],
        "unresolved": counts["unresolved"],
        "positive_labels": counts["label_1"],
        "negative_labels": counts["label_0"],
        "source_authenticity_externally_verified_by_tool": False,
        "ready_for_structural_baseline": True,
        "notes": [
            "A human attestation cannot prove source completeness without a separate scientific audit.",
            "Sampling, independent registry scope and negative-case censoring determine metric validity.",
            "No public wildfire prediction claims are authorized by this export.",
        ],
    }
    return rows, manifest, result


def _write_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with path.open("x", encoding="utf-8") as writer:
            created = True
            writer.write(content)
    except Exception:
        if created:
            path.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent wildfire label research review workbench")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Assemble unlabeled review queue from source and frame")
    prepare.add_argument("--perimeter-db", required=True, type=Path)
    prepare.add_argument("--at", required=True)
    prepare.add_argument("--year", action="append", required=True, type=int)
    prepare.add_argument("--frame", required=True, type=Path)
    prepare.add_argument("--seed", default="wildfire-review-v1")
    prepare.add_argument("--max-controls", type=int, default=80)
    prepare.add_argument("--output", required=True, type=Path)
    finalize = sub.add_parser("finalize", help="Export only explicitly double-adjudicated cases")
    finalize.add_argument("--queue", required=True, type=Path)
    finalize.add_argument("--reviews", required=True, type=Path)
    finalize.add_argument("--protocol", required=True, type=Path)
    finalize.add_argument("--cohort", required=True, type=Path)
    finalize.add_argument("--manifest", required=True, type=Path)
    finalize.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    outputs = ([args.output] if args.command == "prepare" else
               [args.cohort, args.manifest, args.summary])
    inputs = ([args.perimeter_db, args.frame] if args.command == "prepare"
              else [args.queue, args.reviews, args.protocol])
    if (len({p.resolve() for p in outputs}) != len(outputs) or
            any(p.resolve() in {x.resolve() for x in inputs} or p.exists()
                for p in outputs)):
        parser.error("outputs must be new, distinct, and never overwrite source files")
    if args.command == "prepare":
        data = prepare_queue(args.perimeter_db, at=args.at, years=args.year,
                             frame_path=args.frame, seed=args.seed,
                             max_controls=args.max_controls)
        _write_new(args.output, json.dumps(data, indent=2,
                                           ensure_ascii=False, sort_keys=True)+"\n")
        print(json.dumps({"queue":str(args.output), "cases":len(data["cases"]),
                          "independent_labels_created":0},sort_keys=True))
        return
    rows, manifest, summary = finalize_queue(args.queue, args.reviews, args.protocol)
    serialized = [
        "".join(json.dumps(row, sort_keys=True, ensure_ascii=False)+"\n" for row in rows),
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False)+"\n",
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False)+"\n",
    ]
    created = []
    try:
        for path, body in zip(outputs, serialized):
            _write_new(path, body)
            created.append(path)
    except Exception:
        # Never leave a partially exported cohort that might be mistaken for a
        # complete reviewed evidence dataset when a later file cannot be saved.
        for path in created:
            if path.exists():
                path.unlink()
        raise
    print(json.dumps({"cohort":str(args.cohort),
                      "reviewed_rows":summary["adjudicated_rows"],
                      "positive":summary["positive_labels"],
                      "negative":summary["negative_labels"],
                      "externally_verified_by_tool":False},sort_keys=True))


if __name__ == "__main__":
    main()
