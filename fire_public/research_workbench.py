"""An actual offline investigation queue over original-source-replayed event evidence.

Local working notes are a user-controlled browser export; no public event labels,
incident predictions, network calls, or silent persistence are generated.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import csv
import hashlib
import html
import io
import json
from pathlib import Path

from .calfire_ambiguity_dossiers import investigate
from .calfire_blind_review import _digest, _load_votes, _original_cases, _write_new
from .calfire_lineage_audit import analyze as audit_lineage
from .mtbs_candidate_triage import _csv_safe
from .mtbs_event_corroboration import _archive
from .mtbs_match_review import load_study

MAX_REPORT_BYTES = 2 * 1024 * 1024
PRIORITIES = {
    "conflicting_reviewer_leads": (0, "Resolve independent source-lead disagreement"),
    "shared_original_source": (1, "Investigate shared upstream original incident page"),
    "review_citation_gaps": (2, "Capture and authenticate cited original documents"),
    "multiple_official_leads": (3, "Compare competing original CAL FIRE pages independently"),
    "single_name_lead": (4, "Find independently authenticated event identity evidence"),
    "no_name_lead": (5, "Search independent coverage without treating missing lead as no fire"),
    "reviewable_not_authenticated": (6, "External adjudication of physical-event identity required"),
}
PRIORITY_DESCRIPTIONS = {
    "conflicting_reviewer_leads": "Two blinded reviewers chose different official incident pages.",
    "shared_original_source": "At least one original CAL FIRE page is referenced by multiple candidate pairs.",
    "review_citation_gaps": "Agreement exists but supporting document lineage remains unresolved.",
    "multiple_official_leads": "Several official name-linked pages could describe different incidents.",
    "single_name_lead": "One name-linked incident page is not a verified same-event crosswalk.",
    "no_name_lead": "Lack of a CAL FIRE name-linked page cannot establish absence of a wildfire.",
    "reviewable_not_authenticated": "Structural dossier is ready; external provenance is still not authenticated.",
}


def queue(casebook: dict, lineage: dict) -> dict:
    """No risk score: the ordering is exclusively manual investigation workflow."""
    _original_cases(casebook)
    if (lineage.get("research_status") !=
            "private_source_lineage_reconstruction_not_fire_ground_truth"
            or lineage.get("original_casebook_sha256") != _digest(casebook)
            or lineage.get("verified_same_event_crosswalks") != 0
            or lineage.get("verified_nonfire_labels") != 0
            or lineage.get("forecast_skill_measured") is not False
            or lineage.get("original_candidate_population") !=
            casebook["research_candidate_count"]):
        raise ValueError("lineage report not bound to original unverified source population")
    reviewed = {r["candidate_id"]: r for r in lineage.get("cases", [])}
    if len(reviewed) != lineage.get("ambiguous_cases_audited"):
        raise ValueError("duplicate or missing source-lineage review cases")
    cases = casebook["cases"]
    if len({r["candidate_id"] for r in cases}) != len(cases):
        raise ValueError("duplicate source case identifiers")
    ambiguous = {c["candidate_id"] for c in cases if c["source_option_count"] > 1}
    if set(reviewed) != ambiguous:
        raise ValueError("lineage and original multi-option candidate sets disagree")

    pages = {}
    for case in cases:
        if case.get("event_identity_verified") is not False or case.get("fire_absence_verified") is not False:
            raise ValueError("confirmed fire/nonfire claims forbidden in research queue")
        options = case["official_calfire_page_options"]
        if len(options) != case["source_option_count"]:
            raise ValueError("original source option completeness drift")
        for o in options:
            url = o["source_url"]
            sig = o["source_detail_html_sha256"]
            if url in pages and pages[url] != sig:
                raise ValueError("same original incident URL has two SHA fingerprints")
            pages[url] = sig
    if len(pages) != casebook["candidate_linked_unique_pages_verified"]:
        raise ValueError("historical original page coverage incomplete")

    rows = []
    counts = Counter()
    for case in cases:
        cid = case["candidate_id"]
        opts = case["official_calfire_page_options"]
        lineage_row = reviewed.get(cid)
        if len(opts) > 1 and lineage_row is None:
            raise ValueError("ambiguous case silently dropped from provenance")
        reused = any(o["candidate_pair_count_reusing_url"] > 1 for o in opts)
        state = lineage_row["status"] if lineage_row else "needs_independent_original_event_research"
        review = lineage_row["review_status"] if lineage_row else None

        if review == "conflicting_source_leads":
            priority = "conflicting_reviewer_leads"
        elif reused:
            priority = "shared_original_source"
        elif lineage_row and state == "source_lineage_or_citation_gaps":
            priority = "review_citation_gaps"
        elif len(opts) > 1 and state != "structurally_reviewable_not_authenticated":
            priority = "multiple_official_leads"
        elif not opts:
            priority = "no_name_lead"
        elif len(opts) == 1:
            priority = "single_name_lead"
        else:
            priority = "reviewable_not_authenticated"

        code, action = PRIORITIES[priority]
        counts[priority] += 1
        warnings = sorted(set(
            case["unresolved_evidence_gates"] +
            (lineage_row["unresolved_gates"] if lineage_row else [])))
        rows.append({
            "candidate_id": cid,
            "priority_group": priority,
            "priority_order": code,
            "priority_reason": PRIORITY_DESCRIPTIONS[priority],
            "next_action": action,
            "mtbs": {
                "fire_id": case["mtbs_fire_id"], "name": case["mtbs_name"],
                "fire_type": case["mtbs_fire_type"],
                "retrospective_day": case["mtbs_retrospective_source_day"],
            },
            "nifc": {"source_identity": case["nifc_source_identity"],
                     "name": case["nifc_name"],
                     "object_id": case["nifc_object_id"]},
            "original_official_pages": [{
                "source_url": o["source_url"], "source_name": o["source_name"],
                "source_day": o["source_start_day"],
                "source_county": o["source_county_text"],
                "source_point_not_ignition": o["source_location_lat_lon_not_ignition"],
                "source_detail_html_sha256": o["source_detail_html_sha256"],
                "reused_by_candidate_pairs": o["candidate_pair_count_reusing_url"],
                "mtbs_day_gap_not_decision_time": o["mtbs_start_day_gap_abs"],
                "distance_km_not_fire_identity": o["mtbs_centroid_to_source_point_km"],
                "source_issues": o["unresolved_source_signals"],
                "verified_event_identity": False,
            } for o in opts],
            "original_lead_count": len(opts),
            "shared_source_page": reused,
            "lineage_status": state,
            "review_status": review,
            "review_hypothesis": lineage_row["review_hypothesis"] if lineage_row else None,
            "private_document_count": (
                lineage_row["private_documents_archived"] if lineage_row else 0),
            "review_citations": (
                lineage_row["cited_document_links"] if lineage_row else []),
            "unresolved_evidence_gates": warnings,
            "same_physical_event_verified": False,
            "independent_nonfire_verified": False,
            "risk_or_forecast_score": None,
        })
    rows.sort(key=lambda r: (r["priority_order"], -r["original_lead_count"], r["candidate_id"]))
    result = {
        "schema_version": 1,
        "research_status": "private_historical_investigation_queue_not_ground_truth",
        "scientific_maturity": "experimental_offline_evidence_workflow",
        "source_casebook_sha256": _digest(casebook),
        "source_nifc_mtbs_study_sha256": casebook["nifc_mtbs_original_study_sha256"],
        "source_lineage_report_sha256": _digest(lineage),
        "original_candidate_population": len(rows),
        "ambiguous_original_candidates": len(ambiguous),
        "original_official_page_population": len(pages),
        "private_original_document_receipts_checked": lineage["private_receipts_verified"],
        "manual_work_priority_counts": {key: counts[key] for key in PRIORITIES},
        "candidate_linked_pages_not_a_complete_calfire_fire_census": True,
        "retrospective_study_is_not_decision_time_evidence": True,
        "no_confirmed_fire_or_nonfire_labels": True,
        "rows": rows,
        "verified_same_event_crosswalks": 0,
        "verified_nonfire_labels": 0,
        "measured_model_skill": False,
    }
    if len(json.dumps(result, allow_nan=False, ensure_ascii=False).encode()) > MAX_REPORT_BYTES:
        raise ValueError("research queue exceeds bounded JSON budget")
    return result


def csv_queue(report: dict) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(("candidate_id", "manual_priority_group", "next_investigation_action",
                     "mtbs_original_fire_id", "nifc_source_identity",
                     "official_page_options", "shared_original_calfire_page",
                     "review_status", "lineage_status", "private_documents_archived",
                     "unresolved_evidence_gates", "verified_event_identity"))
    for r in report["rows"]:
        values = (r["candidate_id"], r["priority_group"], r["next_action"],
                  r["mtbs"]["fire_id"], r["nifc"]["source_identity"],
                  r["original_lead_count"], r["shared_source_page"],
                  r["review_status"], r["lineage_status"], r["private_document_count"],
                  "; ".join(r["unresolved_evidence_gates"]), False)
        writer.writerow([_csv_safe(x) for x in values])
    return buffer.getvalue()


CSS = """
:root{font-family:system-ui,sans-serif;color-scheme:light;background:#f3f6f7;color:#17323c}
*{box-sizing:border-box}body{margin:0;line-height:1.45}header{background:#173944;color:white;padding:16px 22px}
header h1{font-size:1.5rem;margin:.2rem 0}header p{max-width:75rem;margin:.4rem 0}
.warning{font-weight:650;color:#8a460c}.header-warning{color:#ffe1a2}
main{display:grid;grid-template-columns:minmax(270px,380px) minmax(0,1fr);min-height:70vh}
aside{border-right:1px solid #c7d3d6;padding:18px;background:white}
.content{padding:18px;min-width:0;max-width:1050px}
input,select,textarea,button{font:inherit}input,select,textarea{padding:9px;border:1px solid #697f88;border-radius:5px}
textarea{width:100%;min-height:110px;resize:vertical}
button{padding:8px 12px;background:#215466;color:white;border:0;border-radius:5px;cursor:pointer}
button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #af630b;outline-offset:2px}
button[aria-pressed=true]{background:#8e4a12}button:disabled{opacity:.5;cursor:not-allowed}
.controls{display:grid;gap:8px}.controls label{display:grid;gap:4px}
#case-list{padding:0;list-style:none;margin:12px 0}#case-list li{margin:4px 0}
#case-list button{display:block;width:100%;text-align:left;background:#edf3f4;color:#17323c;border:1px solid #b3c9ce}
#case-list button[aria-pressed=true]{border:2px solid #075d78;background:#d0e9ee}
#case-list small{display:block;color:#385660}.row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
section,article{margin:16px 0 22px}section{border-top:1px solid #becfd2;padding-top:14px}
h2{font-size:1.35rem}h3{font-size:1.06rem}ul{padding-left:20px}li{margin:6px 0;overflow-wrap:anywhere}
.source{padding:12px;margin:8px 0;border:1px solid #b9d0d6;border-radius:7px;background:white}
code{font-size:.84rem;overflow-wrap:anywhere}a{color:#07516d;overflow-wrap:anywhere}
header,aside,.content,#detail,.source{min-width:0;overflow-wrap:anywhere}
input,select{max-width:100%}
#case-list button{overflow-wrap:anywhere;white-space:normal}
.metrics{display:flex;gap:18px;flex-wrap:wrap}.metrics strong{font-variant-numeric:tabular-nums}
.muted{color:#48616e}.status{font-weight:600}#flash{min-height:1.5rem;color:#7c4010}
.action-strip{display:flex;gap:8px;flex-wrap:wrap}#session-file{max-width:260px}
@media(max-width:750px){main{grid-template-columns:1fr}aside{border-right:0;border-bottom:2px solid #93aab1}.content,aside{padding:14px}header{padding:14px}}
"""


def offline_html(report: dict) -> str:
    if (report.get("research_status") !=
            "private_historical_investigation_queue_not_ground_truth" or
            report.get("verified_same_event_crosswalks") != 0 or
            report.get("verified_nonfire_labels") != 0 or
            report.get("measured_model_skill") is not False or
            report.get("no_confirmed_fire_or_nonfire_labels") is not True):
        raise ValueError("forged verified event labels forbidden in investigation workbench")
    payload = base64.b64encode(json.dumps(
        report, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        allow_nan=False).encode("utf-8")).decode("ascii")
    javascript = Path(__file__).with_name("research_workbench.js").read_text(encoding="utf-8")
    script = (javascript + "\nWildfireResearch.mount(document,JSON.parse(new TextDecoder("
              "'utf-8').decode(Uint8Array.from(atob('" + payload +
              "'),c=>c.charCodeAt(0)))));\n")
    token = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    style_token = base64.b64encode(hashlib.sha256(CSS.encode()).digest()).decode()
    policy = ("default-src 'none'; script-src 'sha256-" + token + "'; "
              "style-src 'sha256-" + style_token + "'; connect-src 'none'; img-src 'none'; "
              "object-src 'none'; base-uri 'none'; form-action 'none'")
    e = lambda v: html.escape(v, quote=True)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="' + e(policy) + '">'
            '<title>Private historical wildfire evidence workbench</title><style>' +
            CSS + '</style></head><body>'
            '<header><h1>Historical source investigation workbench</h1>'
            '<p class="header-warning">Experimental, retrospective evidence only. '
            'No independently verified physical wildfire identities, nonfire labels, '
            'or predictive probabilities. Investigation order is NOT fire risk.</p>'
            '<p>Source casebook SHA: <code id="source-hash"></code></p></header>'
            '<main><aside aria-label="Research queue">'
            '<h2>Investigate evidence</h2><div class="metrics" id="queue-counts"></div>'
            '<div class="controls"><label>Search records<input id="search" type="search" '
            'placeholder="Incident, provider, ID or source name"></label>'
            '<label>Work category<select id="priority"><option value="all">All cases</option>'
            '</select></label><label>Review status<select id="work-state">'
            '<option value="all">All working states</option>'
            '<option value="not_started">Not started</option>'
            '<option value="investigating">Investigating</option>'
            '<option value="blocked">Blocked</option>'
            '<option value="request_external_adjudication">External adjudication requested</option>'
            '</select></label></div><p id="visible-count" role="status"></p>'
            '<ol id="case-list"></ol></aside>'
            '<div class="content"><div class="action-strip">'
            '<button type="button" id="download-session">Export private notes JSON</button>'
            '<label>Resume private notes from file <input id="session-file" type="file" '
            'accept=".json,application/json"></label></div>'
            '<p id="flash" role="status" aria-live="polite"></p>'
            '<p class="muted">Notes are in browser memory only until exported. No '
            'network or cloud sync. Import rejects another source casebook.</p>'
            '<div id="detail" tabindex="-1"></div></div></main><script>' +
            script + '</script></body></html>\n')


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Private offline research workflow over exact original fire source bytes")
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--calfire-archive-dir", type=Path, required=True)
    parser.add_argument("--batch", type=Path, action="append", required=True)
    parser.add_argument("--first", type=Path)
    parser.add_argument("--second", type=Path)
    parser.add_argument("--private-receipts", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if (args.first is None) != (args.second is None):
        parser.error("both independent private reviewer files required together")
    sources = [args.study_dir, args.calfire_archive_dir, *args.batch]
    if args.private_receipts is not None:
        store = args.private_receipts
        if (store.is_symlink() or not store.is_dir() or
                store.resolve().is_relative_to(Path(__file__).resolve().parents[1]) or
                any(store.resolve().is_relative_to(s.resolve()) or
                    s.resolve().is_relative_to(store.resolve()) for s in sources)):
            parser.error("private documentary archive must be outside original sources/public Git workspace")
        sources.append(store)
    casebook = investigate(args.study_dir, args.calfire_archive_dir, args.batch)
    receipts = []
    if args.private_receipts is not None:
        _, study_sha, candidates = load_study(args.study_dir)
        if study_sha != casebook["nifc_mtbs_original_study_sha256"]:
            raise ValueError("original source drift before documentary receipt replay")
        receipts = _archive(args.private_receipts, study_sha,
                            {c["candidate_id"]: c for c in candidates})
    first = _load_votes(args.first) if args.first is not None else None
    second = _load_votes(args.second) if args.second is not None else None
    sources += [p for p in (args.first, args.second) if p is not None]
    lineage = audit_lineage(casebook, first, second, receipts)
    report = queue(casebook, lineage)
    data = {
        "index.html": offline_html(report).encode("utf-8"),
        "queue.json": (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True,
                                 allow_nan=False) + "\n").encode("utf-8"),
        "queue.csv": csv_queue(report).encode("utf-8"),
    }
    _write_new(args.output_dir, data, sources)
    print(json.dumps({"investigation_candidates": len(report["rows"]),
                      "ambiguous_candidates": report["ambiguous_original_candidates"],
                      "source_sha256": report["source_casebook_sha256"],
                      "output": sorted(data),
                      "verified_event_labels": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
