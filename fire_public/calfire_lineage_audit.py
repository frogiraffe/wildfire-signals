"""Original-source-replayed provenance and independent-document lineage audit.

Evidence graph is private, bounded and source-hash-bound. A structurally
consistent dossier still does not authenticate an upstream record, same-fire
identity, fire absence, or predictive skill.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path

from .calfire_ambiguity_dossiers import investigate
from .calfire_blind_review import (
    _digest, _load_votes, _original_cases, _write_new, reconcile,
)
from .label_review import _utc
from .mtbs_event_corroboration import _archive
from .mtbs_match_review import load_study

MAX_REPORT_BYTES = 2 * 1024 * 1024
LIMITS = (
    "Same place/name/date or human agreement is not an authenticated same-fire identity.",
    "CAL FIRE, NIFC and MTBS can reproduce a shared upstream incident report.",
    "Different citations and publisher declarations do not prove source independence.",
    "A locally SHA-verified document is not externally authenticated.",
    "Missing evidence, missing CAL FIRE name leads and absent observations are not nonfire labels.",
    "Retrospective records cannot be treated as features available at historical decision time.",
)


def _id(kind: str, value: str) -> str:
    return kind + ":" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _validate_receipts(reports: list[dict], casebook: dict) -> None:
    """Defence in depth for the supplied, already SHA-replayed private receipt store."""
    all_cases = {case["candidate_id"]: case for case in casebook["cases"]}
    for rec in reports:
        case = all_cases.get(rec["candidate_id"])
        if (case is None or rec["source_study_sha256"] !=
                casebook["nifc_mtbs_original_study_sha256"] or
                rec["mtbs_fire_id"] != case["mtbs_fire_id"] or
                rec["nifc_source_identity"] != case["nifc_source_identity"] or
                rec["origin_authenticated_by_tool"] is not False or
                rec["upstream_independence_verified"] is not False):
            raise ValueError("private documentary receipt crosses original-source boundaries")


def analyze(casebook: dict, first: dict | None = None, second: dict | None = None,
            receipts: list[dict] | None = None) -> dict:
    """Combine verified original source pages, private receipts and blind hypotheses."""
    if (first is None) != (second is None):
        raise ValueError("blind reviewer files must be supplied as a pair")
    cases = _original_cases(casebook)
    review = reconcile(casebook, first, second) if first is not None else None
    reviews = {r["candidate_id"]: r for r in review["cases"]} if review else {}
    receipts = receipts or []
    _validate_receipts(receipts, casebook)
    by_case = defaultdict(list)
    for rec in receipts:
        by_case[rec["candidate_id"]].append(rec)

    url_cases = defaultdict(set)
    citation_cases = defaultdict(set)
    for case in casebook["cases"]:
        for option in case["official_calfire_page_options"]:
            url_cases[option["source_url"]].add(case["candidate_id"])
    for cid, row in reviews.items():
        for side in ("first", "second"):
            url = row[side]["external_evidence_url"]
            if url:
                citation_cases[url].add(cid)

    counts = Counter()
    output = []
    graph_nodes: dict[str, dict] = {}
    graph_edges = []

    def node(kind: str, identifier: str, **attributes: object) -> str:
        nid = _id(kind, identifier)
        value = {"id": nid, "kind": kind, **attributes,
                 "independent_origin_verified": False}
        if nid in graph_nodes and graph_nodes[nid] != value:
            raise ValueError("conflicting metadata for same source graph identity")
        graph_nodes[nid] = value
        return nid

    def edge(source: str, dest: str, kind: str, **data: object) -> None:
        graph_edges.append({"from": source, "to": dest, "relation": kind, **data,
                            "physical_event_identity_proven": False})

    for cid, case in cases.items():
        case_node = node("candidate_pair", cid, candidate_id=cid)
        nifc = node("nifc_original_record", case["nifc_source_identity"],
                    source_identity=case["nifc_source_identity"])
        mtbs = node("mtbs_original_record", str(case["mtbs_fire_id"]),
                    source_identity=str(case["mtbs_fire_id"]))
        edge(case_node, nifc, "retrospective_geographic_candidate")
        edge(case_node, mtbs, "retrospective_geographic_candidate")

        issues = set()
        alternatives = []
        for option in case["official_calfire_page_options"]:
            url = option["source_url"]
            ref = node("calfire_original_page", url, source_url=url,
                       original_html_sha256=option["source_detail_html_sha256"])
            edge(case_node, ref, "name_only_official_page_lead")
            if len(url_cases[url]) > 1:
                issues.add("original_calfire_page_reused_across_candidate_pairs")
            alternatives.append({"url": url,
                                 "source_sha256": option["source_detail_html_sha256"],
                                 "candidate_reuse_count": len(url_cases[url])})

        row = reviews.get(cid)
        docs = by_case[cid]
        cited = []
        matched = []
        if row is None:
            issues.add("two_completed_blind_reviews_missing")
        else:
            if row["status"] != "concordant_unverified_lead":
                issues.add("blind_reviews_disagree_or_remain_unresolved")
            if "reviewer_reports_common_upstream_source" in row["research_flags"]:
                issues.add("reviewer_declares_shared_upstream")
            for side in ("first", "second"):
                vote = row[side]
                url = vote["external_evidence_url"]
                if not url:
                    continue
                if url in url_cases:
                    issues.add("cited_original_calfire_page_is_not_independent_evidence")
                if len(citation_cases[url]) > 1:
                    issues.add("review_citation_reused_across_candidate_pairs")
                matching = [d for d in docs if d["source_url"] == url]
                if len(matching) != 1:
                    issues.add("review_citation_not_uniquely_archived_for_candidate")
                entry = {"reviewer": side, "citation_url": url,
                         "matching_receipt_count": len(matching),
                         "citation_shared_across_candidates": len(citation_cases[url]) > 1}
                if len(matching) == 1:
                    rec = matching[0]
                    entry["document_sha256"] = rec["document_sha256"]
                    entry["receipt_id"] = rec["receipt_id"]
                    matched.append(rec)
                    # Reviewers cannot have inspected a document first captured later
                    # in our private archive without extra independent provenance.
                    if _utc(rec["captured_at"]) > _utc(vote["reviewed_at"]):
                        issues.add("evidence_document_archived_after_reviewer_vote")
                    if _utc(rec["source_published_at"]) > _utc(vote["reviewed_at"]):
                        issues.add("evidence_document_published_after_reviewer_vote")
                cited.append(entry)
            if (row["first"]["external_evidence_url"] and
                    row["first"]["external_evidence_url"] ==
                    row["second"]["external_evidence_url"]):
                issues.add("reviewers_cited_same_source_url")

        for rec in docs:
            rid = rec["receipt_id"]
            ref = node("private_document_receipt", rid,
                       receipt_id=rid, document_sha256=rec["document_sha256"],
                       source_url=rec["source_url"],
                       declared_publisher=rec["publisher_id"],
                       declared_upstream_family=rec["upstream_family"],
                       source_published_at=rec["source_published_at"],
                       captured_at=rec["captured_at"])
            edge(case_node, ref, "locally_sha_verified_third_party_document_claim")
            for side in ("first", "second"):
                if row and row[side]["external_evidence_url"] == rec["source_url"]:
                    edge(case_node, ref, "reviewer_cited_document",
                         reviewer_side=side, reviewer_id=row[side]["reviewer_id"])

        if row and row["status"] == "concordant_unverified_lead":
            # Two distinct citations are required; even then declared upstream
            # publisher/family/firsthand status is NOT external authentication.
            if len(matched) != 2 or len({r["receipt_id"] for r in matched}) != 2:
                issues.add("two_distinct_original_documents_not_cited")
            if len({r["publisher_id"].casefold() for r in matched}) < 2:
                issues.add("distinct_declared_publishers_missing")
            if len({r["upstream_family"].casefold() for r in matched}) < 2:
                issues.add("distinct_declared_upstream_families_missing")
            if len({r["source_record_id"].casefold() for r in matched}) < 2:
                issues.add("distinct_declared_source_record_ids_missing")
            if len({r["document_sha256"] for r in matched}) < 2:
                issues.add("identical_document_bytes_reused_as_two_sources")
            if any(r["upstream_role"] != "firsthand_original_record" for r in matched):
                issues.add("secondary_or_unknown_upstream_source")
            if any(r["relation_claim"] != "same_event_document_claim" for r in matched):
                issues.add("third_party_document_does_not_claim_same_event")
            if any(r["source_event_at"] is None for r in matched):
                issues.add("third_party_source_event_time_missing")
            elif len({r["source_event_at"][:10] for r in matched}) != 1:
                issues.add("independent_documents_disagree_on_event_day")
            if (row["agreed_lead_hypothesis"] not in
                    {o["source_url"] for o in case["official_calfire_page_options"]}):
                raise ValueError("review selected source not in original candidate options")

        if row is None:
            status = "awaiting_independent_human_reviews"
        elif row["status"] != "concordant_unverified_lead":
            status = "unresolved_human_hypotheses"
        elif issues:
            status = "source_lineage_or_citation_gaps"
        else:
            status = "structurally_reviewable_not_authenticated"
        counts[status] += 1
        output.append({
            "candidate_id": cid, "status": status,
            "original_calfire_alternatives": alternatives,
            "review_hypothesis": row["agreed_lead_hypothesis"] if row else None,
            "review_status": row["status"] if row else None,
            "cited_document_links": cited,
            "private_documents_archived": len(docs),
            "unresolved_gates": sorted(issues),
            "authenticated_same_physical_event": False,
            "independent_source_lineage_proven": False,
            "verified_fire_presence_or_absence": False,
        })

    nodes = sorted(graph_nodes.values(), key=lambda x: x["id"])
    graph_edges.sort(key=lambda x: (x["from"], x["to"], x["relation"],
                                   x.get("reviewer_side", "")))
    result = {
        "schema_version": 1,
        "research_status": "private_source_lineage_reconstruction_not_fire_ground_truth",
        "original_casebook_sha256": _digest(casebook),
        "original_nifc_mtbs_study_sha256":
            casebook["nifc_mtbs_original_study_sha256"],
        "review_hypotheses_sha256": _digest(review) if review else None,
        "original_candidate_population": casebook["research_candidate_count"],
        "ambiguous_cases_audited": len(output),
        "private_receipts_verified": len(receipts),
        "statuses": {key: counts[key] for key in (
            "awaiting_independent_human_reviews",
            "unresolved_human_hypotheses",
            "source_lineage_or_citation_gaps",
            "structurally_reviewable_not_authenticated")},
        "cases": output,
        "evidence_graph": {"nodes": nodes, "edges": graph_edges,
                           "independent_upstream_origins_authenticated": 0},
        "verified_same_event_crosswalks": 0,
        "verified_nonfire_labels": 0,
        "forecast_skill_measured": False,
        "limitations": list(LIMITS),
    }
    if len(json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8")) > MAX_REPORT_BYTES:
        raise ValueError("private lineage report exceeds bounded size")
    return result


def offline_html(report: dict) -> str:
    if (report.get("research_status") !=
            "private_source_lineage_reconstruction_not_fire_ground_truth" or
            report.get("verified_same_event_crosswalks") != 0 or
            report.get("verified_nonfire_labels") != 0 or
            report.get("forecast_skill_measured") is not False):
        raise ValueError("must not render a fabricated validated source lineage")
    e = lambda value: html.escape(str(value), quote=True)
    cases = []
    for case in report["cases"]:
        links = "".join("<li>" + e(o["url"]) + " (SHA " +
                        e(o["source_sha256"]) + ", shared " +
                        e(o["candidate_reuse_count"]) + " candidate(s))</li>"
                        for o in case["original_calfire_alternatives"])
        citations = "".join("<li>" + e(v["reviewer"]) + ": " +
                            e(v["citation_url"]) + "; archived receipts " +
                            e(v["matching_receipt_count"]) + "</li>"
                            for v in case["cited_document_links"])
        cases.append("<section><h2>" + e(case["candidate_id"]) + "</h2>"
                     "<p>Review: " + e(case["status"]) + "; lead: " +
                     e(case["review_hypothesis"]) + "</p>"
                     "<h3>Original CAL FIRE alternatives</h3><ul>" + links +
                     "</ul><h3>Reviewer citations</h3><ul>" + citations +
                     "</ul><p>Unresolved evidence gates: " +
                     e(", ".join(case["unresolved_gates"]) or
                       "Structural checks met; source origins still unauthenticated") +
                     "</p></section>")
    css = ("body{font:1rem/1.5 system-ui;max-width:72rem;margin:2rem auto;padding:1rem}"
           "section{border-top:1px solid #aaa;padding:1rem 0}"
           "code,li,p{overflow-wrap:anywhere}.warning{font-weight:600;color:#91470a}")
    style_hash = base64.b64encode(hashlib.sha256(css.encode()).digest()).decode()
    csp = ("default-src 'none'; script-src 'none'; connect-src 'none'; img-src 'none'; "
           "object-src 'none'; base-uri 'none'; style-src 'sha256-" + style_hash + "'")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="' + e(csp) + '">'
            '<title>Private event-lineage research audit</title><style>' + css +
            '</style></head><body><h1>Historical source lineage reconstruction</h1>'
            '<p class="warning">Every physical wildfire identity remains unverified; '
            'no verified nonfire or forecast skill.</p>'
            '<p>Original study SHA-256: <code>' +
            e(report["original_nifc_mtbs_study_sha256"]) + '</code></p>' +
            "".join(cases) + '</body></html>\n')


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Private historical original-source lineage audit, not fire truth")
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--calfire-archive-dir", type=Path, required=True)
    parser.add_argument("--batch", type=Path, action="append", required=True)
    parser.add_argument("--first", type=Path)
    parser.add_argument("--second", type=Path)
    parser.add_argument("--private-receipts", type=Path,
                        help="Pre-existing private mtbs_event_corroboration capture store")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if (args.first is None) != (args.second is None):
        parser.error("both independent reviewer vote files are required together")
    sources = [args.study_dir, args.calfire_archive_dir, *args.batch]
    if args.private_receipts is not None:
        store = args.private_receipts
        if (store.is_symlink() or not store.is_dir() or
                store.resolve().is_relative_to(Path(__file__).resolve().parents[1])):
            parser.error("existing private evidence store must be outside public Git repository")
        if (any(store.resolve().is_relative_to(s.resolve()) or
                s.resolve().is_relative_to(store.resolve()) for s in sources)):
            parser.error("private receipt store cannot overlap original source archives")
        sources.append(store)
    casebook = investigate(args.study_dir, args.calfire_archive_dir, args.batch)
    receipts = []
    if args.private_receipts is not None:
        study, sha, cases = load_study(args.study_dir)
        if sha != casebook["nifc_mtbs_original_study_sha256"]:
            raise ValueError("original source study SHA drift before private receipt loading")
        receipts = _archive(args.private_receipts, sha,
                            {case["candidate_id"]: case for case in cases})
    first = _load_votes(args.first) if args.first is not None else None
    second = _load_votes(args.second) if args.second is not None else None
    sources += [p for p in (args.first, args.second) if p is not None]
    result = analyze(casebook, first, second, receipts)
    _write_new(args.output_dir, {
        "private-lineage-audit.json":
            (json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2,
                        allow_nan=False) + "\n").encode(),
        "private-lineage-audit.html": offline_html(result).encode(),
    }, sources)
    print(json.dumps({
        "ambiguous_cases": result["ambiguous_cases_audited"],
        "private_receipts_sha_verified": result["private_receipts_verified"],
        "statuses": result["statuses"],
        "verified_event_identities": 0,
        "verified_nonfire": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
