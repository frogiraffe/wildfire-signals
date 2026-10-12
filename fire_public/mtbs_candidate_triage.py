"""Offline source-backed MTBS/NIFC candidate triage for human investigation.

Ranks REVIEW WORK needed, never wildfire match likelihood. Inputs are original
source-byte-verified aligned studies, optionally independently validated
private votes. No synthetic human votes, nonfire labels or event identities.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import html
import io
import json
from pathlib import Path
import re
import unicodedata

from .mtbs_match_review import load_study
from .mtbs_pair_reconcile import reconcile

GENERIC = frozenset({"fire", "incident", "wildfire", "the"})
PRIORITIES = ("unresolved_review_conflict", "source_identity_ambiguous",
              "source_quality_follow_up", "routine_manual_review")
MAX_OUTPUT = 2 * 1024 * 1024

CSS = """
:root{font-family:system-ui,sans-serif;color-scheme:light;background:#eff3f5;color:#15303c}
body{max-width:1280px;margin:0 auto;padding:20px;line-height:1.5}
header,main,footer{background:white;border:1px solid #cbd5db;border-radius:10px;padding:20px;margin:12px 0}
h1{font-size:1.6rem}h2{font-size:1.2rem}
table{border-collapse:collapse;width:100%;font-size:.94rem}
th,td{border-bottom:1px solid #cad7dc;padding:10px;text-align:left;vertical-align:top}
th{background:#edf3f4}td{overflow-wrap:anywhere}
.warning{color:#87500d}.quiet{color:#465e69}
code{overflow-wrap:anywhere}
@media(max-width:800px){body{padding:8px}header,main,footer{padding:10px}
thead{display:none}table,tr,td,tbody{display:block}tr{border-bottom:2px solid #7b9aa7}
td{border:0;padding:5px}td:before{content:attr(data-label) ": ";font-weight:700}}
"""


def _distinctive_tokens(value: object) -> set[str]:
    """Unicode-aware provider-name tokens, not a verified identity key."""
    if not isinstance(value, str) or not value.strip():
        return set()
    norm = unicodedata.normalize("NFKC", value).casefold()[:512]
    cleaned = "".join(ch if unicodedata.category(ch)[0] in "LN" else " " for ch in norm)
    return set(cleaned.split()) - GENERIC


def _name_relation(a: object, b: object) -> tuple[str, float | None]:
    left, right = _distinctive_tokens(a), _distinctive_tokens(b)
    if not left or not right:
        return "not_comparable_distinctive_name", None
    score = len(left & right) / len(left | right)
    if left == right:
        return "same_distinctive_tokens_not_event_identity", round(score, 4)
    if left & right:
        return "some_distinctive_tokens_shared", round(score, 4)
    return "no_distinctive_tokens_shared", 0.0


def _csv_safe(value: object) -> object:
    """Prevent formula evaluation when exporting untrusted agency/reviewer text."""
    if not isinstance(value, str):
        return value
    if value and (value[0] in "=+-@\t\r\n" or
                  value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@"))):
        return "'" + value
    return value


def analyze(study_dir: Path, first: Path | None = None,
            second: Path | None = None) -> dict:
    if (first is None) != (second is None):
        raise ValueError("provide both independent review files or neither")
    report, study_sha, cases = load_study(study_dir)
    if not cases:
        raise ValueError("source study has no geographic candidates to triage")
    human = None
    reviewed_by_case = {}
    if first is not None:
        human = reconcile(study_dir, first, second)
        if human["source_study_sha256"] != study_sha:
            raise ValueError("human reviews do not belong to original source bundle")
        reviewed_by_case = {x["candidate_id"]: x for x in human["candidates"]}
    mtbs_counts = Counter(x["mtbs"]["object_id"] for x in cases)
    nifc_counts = Counter(x["nifc"]["object_id"] for x in cases)
    data = []
    buckets = Counter()
    relations = Counter()
    for case in cases:
        mtbs, nifc = case["mtbs"], case["nifc"]
        relation, overlap = _name_relation(mtbs["name"], nifc["name"])
        multiple = (mtbs_counts[mtbs["object_id"]] > 1 or
                    nifc_counts[nifc["object_id"]] > 1)
        fire_type = (mtbs["fire_type"] or "").strip().casefold() if isinstance(
            mtbs["fire_type"], str) else ""
        flags = []
        if multiple:
            flags.append("source_record_has_multiple_spatial_candidates")
        if fire_type != "wildfire":
            flags.append("mtbs_fire_type_not_plain_wildfire")
        if mtbs["source_ignition_at"] is None:
            flags.append("mtbs_retrospective_ignition_date_missing")
        flags.append("comparable_nifc_ignition_date_not_established")
        if relation == "no_distinctive_tokens_shared":
            flags.append("source_names_have_no_distinctive_token_overlap")
        if relation == "not_comparable_distinctive_name":
            flags.append("names_lack_distinctive_comparable_tokens")
        review = reviewed_by_case.get(case["candidate_id"])
        disposition = review["review_status"] if review else "not_reviewed"
        if disposition in ("conflicting_hypotheses", "partially_inconclusive"):
            priority = "unresolved_review_conflict"
        elif multiple:
            priority = "source_identity_ambiguous"
        elif fire_type != "wildfire" or mtbs["source_ignition_at"] is None or (
                relation in ("no_distinctive_tokens_shared",
                             "not_comparable_distinctive_name")):
            priority = "source_quality_follow_up"
        else:
            priority = "routine_manual_review"
        buckets[priority] += 1
        relations[relation] += 1
        data.append({
            "candidate_id": case["candidate_id"],
            "priority": priority,
            "priority_is_workload_not_match_probability": True,
            "year": case["year"],
            "mtbs_object_id": mtbs["object_id"],
            "mtbs_fire_id": mtbs["fire_id"],
            "mtbs_name": mtbs["name"],
            "mtbs_fire_type": mtbs["fire_type"],
            "mtbs_retrospective_date": mtbs["source_ignition_at"],
            "mtbs_mapped_longitude": mtbs["longitude"],
            "mtbs_mapped_latitude": mtbs["latitude"],
            "nifc_object_id": nifc["object_id"],
            "nifc_global_id": nifc["source_identity"],
            "nifc_name": nifc["name"],
            "name_relation": relation,
            "descriptive_distinctive_token_jaccard": overlap,
            "mtbs_candidate_degree": mtbs_counts[mtbs["object_id"]],
            "nifc_candidate_degree": nifc_counts[nifc["object_id"]],
            "source_review_flags": flags,
            "review_status": disposition,
            "reviewer_hypothesis_agreement": (
                review["agreed_hypothesis"] if review else None),
            "source_evidence_relation": (
                review["cited_evidence_relation"] if review else "not_reviewed"),
            "same_fire_event_verified": False,
            "independent_outcome_verified": False,
        })
    data.sort(key=lambda x: (
        PRIORITIES.index(x["priority"]), x["candidate_id"]))
    source_pop = report["source_population"]
    return {
        "schema_version": 1,
        "status": "retrospective_human_work_queue_not_fire_event_matching",
        "source_bundle_sha256": study_sha,
        "study_captured_at": report["retrieved_at"],
        "year": report["year"],
        "region_wgs84_bbox": report["roi_wgs84_bbox"],
        "candidate_radius_km": report["candidate_radius_km"],
        "source_population": {
            "nifc_roi_published_object_ids": source_pop["nifc_roi_object_ids"],
            "mtbs_roi_published_object_ids": source_pop["mtbs_roi_object_ids"],
            "nifc_selected_records": len(report["nifc_polygons"]),
            "mtbs_selected_records": len(report["mtbs_points"]),
            "both_selections_exhaust_published_roi_ids":
                source_pop["both_selected_records_exhaust_all_source_roi_ids"],
        },
        "human_review_inputs_provided": human is not None,
        "review_vote_sha256s": (
            [x["vote_sha256"] for x in human["reviewers"]] if human else []),
        "review_status_counts": human["dispositions"] if human else None,
        "candidate_count": len(data),
        "work_priorities": {key: buckets[key] for key in PRIORITIES},
        "name_relation_counts": {key: relations[key] for key in (
            "same_distinctive_tokens_not_event_identity",
            "some_distinctive_tokens_shared",
            "no_distinctive_tokens_shared",
            "not_comparable_distinctive_name")},
        "candidates": data,
        "ground_truth_identity_verified": 0,
        "independent_nonfire_labels_created": 0,
        "prediction_accuracy_measured": False,
        "notes": [
            "Priority is an explicit deterministic RESEARCH WORK queue, not a model, classifier, match probability or truth.",
            "Token overlap does not establish an event identity; very common words like 'fire' are excluded.",
            "NIFC fire year is not an ignition date; MTBS dates are retrospective source attributes.",
            "Many-to-many proximity candidate relationships must not be converted to one-to-one matches.",
            "Prescribed burns, missing names/dates, omitted fires and missing source coverage are NOT verified nonfire labels.",
            "Two human opinions and distinct evidence URLs cannot guarantee independent outcomes.",
            "Source ROI object-ID counts describe the provider's published records, not all wildfire events.",
        ],
    }


def to_csv(result: dict) -> str:
    cols = ("candidate_id", "priority", "review_status", "year",
            "mtbs_fire_id", "mtbs_name", "mtbs_fire_type", "mtbs_retrospective_date",
            "nifc_global_id", "nifc_name", "name_relation",
            "descriptive_distinctive_token_jaccard", "mtbs_candidate_degree",
            "nifc_candidate_degree", "source_evidence_relation")
    buf = io.StringIO(newline="")
    writer = csv.writer(buf)
    writer.writerow(cols)
    for item in result["candidates"]:
        writer.writerow([_csv_safe(item.get(field)) for field in cols])
    return buf.getvalue()


def to_html(result: dict) -> str:
    if (result.get("status") != "retrospective_human_work_queue_not_fire_event_matching" or
            result.get("ground_truth_identity_verified") != 0 or
            result.get("independent_nonfire_labels_created") != 0):
        raise ValueError("only nonlabel research triage results may be rendered")
    esc = lambda x: html.escape(str(x), quote=True)
    rows = []
    for case in result["candidates"]:
        fields = (
            ("Work priority", case["priority"]),
            ("Candidate", case["candidate_id"]),
            ("MTBS", f"{case['mtbs_name']} (ID {case['mtbs_fire_id']}, {case['mtbs_fire_type']})"),
            ("NIFC", f"{case['nifc_name']} (ID {case['nifc_object_id']})"),
            ("Names", case["name_relation"]),
            ("Multiplicity", f"MTBS {case['mtbs_candidate_degree']} / NIFC {case['nifc_candidate_degree']}"),
            ("Review", case["review_status"]),
            ("Follow-up", "; ".join(case["source_review_flags"])),
        )
        rows.append("<tr>" + "".join(
            '<td data-label="' + esc(label) + '">' + esc(value) + "</td>"
            for label, value in fields) + "</tr>")
    css_sha = __import__("base64").b64encode(hashlib.sha256(CSS.encode()).digest()).decode()
    csp = ("default-src 'none'; script-src 'none'; img-src 'none'; "
           "connect-src 'none'; object-src 'none'; base-uri 'none'; "
           "style-src 'sha256-" + css_sha + "'")
    populations = result["source_population"]
    stats = "; ".join(f"{name.replace('_', ' ')}: {value}" for name, value
                      in result["work_priorities"].items())
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + esc(csp) + '">'
        "<title>NIFC–MTBS research workload triage</title><style>" + CSS +
        "</style></head><body><header><h1>Retrospective research workload triage</h1>"
        '<p class="warning">These priorities allocate human research effort, not fire-event '
        'identity, wildfire risk or matching probabilities. Zero independently verified event '
        'identities and zero nonfire labels.</p>'
        "<p>Original study SHA-256: <code>" + esc(result["source_bundle_sha256"]) +
        "</code></p><p>Year: " + esc(result["year"]) + " · Region: " +
        esc(result["region_wgs84_bbox"]) + "</p>"
        "<p>Published source ObjectIDs within ROI: NIFC " +
        esc(populations["nifc_roi_published_object_ids"]) + "; MTBS " +
        esc(populations["mtbs_roi_published_object_ids"]) +
        ". Sampled records are not a complete wildfire census.</p>"
        "<p>Review files included: " + esc(result["human_review_inputs_provided"]) +
        "</p></header><main><h2>Work queue</h2><p>" + esc(stats) +
        "</p><table><thead><tr>" + "".join("<th scope='col'>" + esc(x) +
        "</th>" for x in ("Work priority", "Candidate", "MTBS", "NIFC",
                          "Names", "Multiplicity", "Review", "Follow-up")) +
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></main>"
        '<footer class="quiet">All original provider geometry and incident attributes '
        'are verified by the source study loader. MTBS and NIFC may share agency inputs. '
        'Review disagreement is not a false positive or a false negative.</footer>'
        "</body></html>\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Source-verified NIFC/MTBS research-work triage (NOT identity matching)")
    parser.add_argument("--study-dir", required=True, type=Path)
    parser.add_argument("--first", type=Path)
    parser.add_argument("--second", type=Path)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--html", required=True, type=Path)
    args = parser.parse_args()
    outputs = (args.json, args.csv, args.html)
    inputs = tuple(x for x in (args.first, args.second) if x is not None)
    if (len(set(p.resolve() for p in outputs)) != 3 or
            any(p.exists() or p.resolve().is_relative_to(args.study_dir.resolve())
                or p.resolve() in {x.resolve() for x in inputs} for p in outputs)):
        parser.error("all three outputs must be new, distinct and outside original study/private votes")
    result = analyze(args.study_dir, args.first, args.second)
    files = ((args.json, json.dumps(result, indent=2, ensure_ascii=False,
                                   sort_keys=True) + "\n"),
             (args.csv, to_csv(result)), (args.html, to_html(result)))
    if any(len(data.encode()) > MAX_OUTPUT for _, data in files):
        raise ValueError("human research triage report exceeds output budget")
    written = []
    try:
        for path, data in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as stream:
                stream.write(data)
            written.append(path)
    except BaseException:
        for path in written:
            path.unlink()
        raise
    print(json.dumps({
        "source_candidates": result["candidate_count"],
        "work_priorities": result["work_priorities"],
        "verified_event_identities": 0,
        "binary_labels_created": 0,
        "output_json": str(args.json)}, sort_keys=True))


if __name__ == "__main__":
    main()
