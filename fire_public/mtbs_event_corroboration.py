"""Private third-party document dossier for NIFC–MTBS event crosswalk research.

This intentionally cannot assert verified event identity. It snapshots exact
human-acquired third-party source documents and compares provenance claims to
original two-provider records and independent human review citations. Two
declared different publishers are not proof of truly independent reporting.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import base64
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

from .evidence_receipts import _archive_new
from .label_review import _utc
from .mtbs_match_review import load_study, _url, _bounded_file
from .mtbs_pilot import BASE as MTBS_BASE
from .official_perimeters import SERVICE as NIFC_SERVICE
from .mtbs_pair_reconcile import reconcile

MAX_DOCUMENT = 5 * 1024 * 1024
MAX_METADATA = 24 * 1024
MAX_RECEIPT = 28 * 1024
MAX_RECEIPTS = 128
MAX_REPORT = 512 * 1024
CLAIMS = {"same_event_document_claim", "different_event_document_claim", "uncertain"}
SCOPE = {"firsthand_original_record", "secondary_compilation", "unknown_upstream"}


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _named(value: object, what: str, *, minimum: int = 2, maximum: int = 180) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ValueError(f"{what} must be a nonempty bounded string")
    return value.strip()


def _source_meta(meta: dict, case: dict) -> dict:
    if not isinstance(meta, dict) or meta.get("schema_version") != 1:
        raise ValueError("source corroboration metadata schema_version 1 required")
    if (meta.get("candidate_id") != case["candidate_id"] or
            meta.get("mtbs_fire_id") != case["mtbs"]["fire_id"] or
            type(meta.get("nifc_object_id")) is not int or
            meta["nifc_object_id"] != case["nifc"]["object_id"] or
            meta.get("nifc_source_identity") != case["nifc"]["source_identity"]):
        raise ValueError("third-party document source identities do not match original candidate")
    source_url = meta.get("source_url")
    rights = meta.get("rights_url")
    if not _url(source_url) or not _url(rights):
        raise ValueError("source and rights must be bounded public HTTPS URLs")
    if (source_url.startswith(MTBS_BASE) or source_url.startswith(NIFC_SERVICE)):
        raise ValueError("original NIFC/MTBS source cannot masquerade as third-party corroboration")
    claim = meta.get("relation_claim")
    if claim not in CLAIMS:
        raise ValueError("third-party source must declare same/different/uncertain claim")
    kind = meta.get("upstream_role")
    if kind not in SCOPE:
        raise ValueError("third-party source upstream role must be declared")
    published = _utc(meta.get("source_published_at"))
    event_at = meta.get("source_event_at")
    if event_at is not None:
        event_at = _utc(event_at)
        if event_at > published:
            raise ValueError("retrospective event observation cannot postdate source publication")
    return {
        "schema_version": 1,
        "candidate_id": case["candidate_id"],
        "mtbs_fire_id": case["mtbs"]["fire_id"],
        "nifc_object_id": case["nifc"]["object_id"],
        "nifc_source_identity": case["nifc"]["source_identity"],
        "source_url": source_url,
        "rights_url": rights,
        "publisher_id": _named(meta.get("publisher_id"), "publisher ID"),
        "upstream_family": _named(meta.get("upstream_family"), "declared upstream lineage"),
        "source_record_id": _named(meta.get("source_record_id"), "original third-party source ID"),
        "source_kind": _named(meta.get("source_kind"), "source kind"),
        "upstream_role": kind,
        "relation_claim": claim,
        "source_published_at": published.isoformat(),
        "source_event_at": event_at.isoformat() if event_at is not None else None,
        "researcher_note": _named(meta.get("researcher_note"), "researcher provenance note", minimum=15, maximum=1200),
        "origin_authenticated_by_tool": False,
        "upstream_independence_verified": False,
    }


def prepare(study_dir: Path) -> dict:
    study, study_sha, cases = load_study(study_dir)
    return {
        "schema_version": 1,
        "status": "unadjudicated_third_party_event_corroboration_queue",
        "source_study_sha256": study_sha,
        "source_capture_at": study["retrieved_at"],
        "year": study["year"],
        "region": study["roi_wgs84_bbox"],
        "candidate_count": len(cases),
        "cases": [{
            "candidate_id": c["candidate_id"],
            "mtbs_fire_id": c["mtbs"]["fire_id"],
            "mtbs_object_id": c["mtbs"]["object_id"],
            "mtbs_source_name": c["mtbs"]["name"],
            "mtbs_original_date": c["mtbs"]["source_ignition_at"],
            "mtbs_fire_type": c["mtbs"]["fire_type"],
            "nifc_object_id": c["nifc"]["object_id"],
            "nifc_source_identity": c["nifc"]["source_identity"],
            "nifc_original_name": c["nifc"]["name"],
            "documentary_sources_collected": 0,
            "identity_corroboration_verified": False,
            "recommended_evidence": [
                "Original independent incident report with explicit source event ID",
                "Source publication time and observed event time or honest missingness",
                "Provider lineage and whether it may reuse NIFC/MTBS inputs",
                "Separately archived exact cited documents for each human reviewer",
            ],
        } for c in cases],
        "verified_event_identities": 0,
        "verified_nonfire_labels": 0,
        "note": "This is a blank real-source casebook. No fake third-party records or reviewer conclusions are supplied.",
    }


def capture(study_dir: Path, store: Path, metadata: Path, document: Path,
            *, captured_at: str | None = None) -> dict:
    _, study_sha, cases = load_study(study_dir)
    by_id = {c["candidate_id"]: c for c in cases}
    raw_meta = json.loads(_bounded_file(metadata, MAX_METADATA))
    if raw_meta.get("candidate_id") not in by_id:
        raise ValueError("source case is not in original byte-verified research study")
    values = _source_meta(raw_meta, by_id[raw_meta["candidate_id"]])
    bytes_data = _bounded_file(document, MAX_DOCUMENT)
    received = _utc(captured_at or datetime.now(timezone.utc).isoformat())
    if received < _utc(values["source_published_at"]):
        raise ValueError("document cannot be archived before its declared source publication")
    if not store.is_dir() or store.is_symlink():
        raise ValueError("private evidence store must exist and cannot be a symlink")
    if any(p.resolve().is_relative_to(store.resolve()) for p in (document, metadata)):
        raise ValueError("input documents must be outside the private archive")
    blob_digest = _digest(bytes_data)
    claim = {
        **values,
        "source_study_sha256": study_sha,
        "captured_at": received.isoformat(),
        "document_sha256": blob_digest,
        "document_bytes": len(bytes_data),
        "receipt_purpose": "operator_captured_third_party_crosswalk_claim_not_verified_identity",
    }
    rid = _digest(_canonical(claim))
    receipt = {**claim, "receipt_id": rid}
    base = store / "event-corroboration"
    if (base.is_symlink() or (base / "blobs").is_symlink() or
            (base / "receipts").is_symlink()):
        raise ValueError("event corroboration archive parents cannot be symlinked")
    _archive_new(base / "blobs" / (blob_digest + ".bin"), bytes_data)
    _archive_new(base / "receipts" / (rid + ".json"), _canonical(receipt))
    return receipt


def _archive(store: Path, study_sha: str, by_id: dict[str, dict]) -> list[dict]:
    base = store / "event-corroboration"
    receipts = base / "receipts"
    if (store.is_symlink() or base.is_symlink() or receipts.is_symlink() or
            (base / "blobs").is_symlink()):
        raise ValueError("source archive symlink not permitted")
    if not receipts.exists():
        return []
    if not receipts.is_dir():
        raise ValueError("source receipt archive must be a regular directory")
    files = sorted(receipts.iterdir())
    if len(files) > MAX_RECEIPTS:
        raise ValueError("third-party receipt count exceeds bounded budget")
    result = []
    for path in files:
        if (path.suffix != ".json" or len(path.stem) != 64 or
                any(c not in "0123456789abcdef" for c in path.stem)):
            raise ValueError("unrecognized third-party source receipt filename")
        receipt_bytes = _bounded_file(path, MAX_RECEIPT)
        rec = json.loads(receipt_bytes)
        rid = rec.get("receipt_id")
        if (rid != path.stem or
                _digest(_canonical({k: v for k, v in rec.items() if k != "receipt_id"})) != rid or
                receipt_bytes != _canonical(rec)):
            raise ValueError("third-party receipt content integrity mismatch")
        cid = rec.get("candidate_id")
        if cid not in by_id or rec.get("source_study_sha256") != study_sha:
            raise ValueError("document belongs to another original source study/candidate")
        expected = _source_meta(rec, by_id[cid])
        if any(rec.get(k) != v for k, v in expected.items()):
            raise ValueError("original provider identities or third-party scope changed")
        if rec.get("receipt_purpose") != "operator_captured_third_party_crosswalk_claim_not_verified_identity":
            raise ValueError("cannot promote third-party source document to ground truth")
        published = _utc(rec["source_published_at"])
        received = _utc(rec["captured_at"])
        if received < published:
            raise ValueError("source was captured before declared publication")
        digest = rec.get("document_sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(
                c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid archived third-party document digest")
        source = base / "blobs" / (digest + ".bin")
        data = _bounded_file(source, MAX_DOCUMENT)
        if _digest(data) != digest or len(data) != rec.get("document_bytes"):
            raise ValueError("third-party original source bytes SHA-256 mismatch")
        result.append(rec)
    return result


def audit(study_dir: Path, store: Path, first: Path | None = None,
          second: Path | None = None) -> dict:
    if (first is None) != (second is None):
        raise ValueError("two separate human reviewer files required together")
    study, study_sha, cases = load_study(study_dir)
    by_id = {c["candidate_id"]: c for c in cases}
    receipts = _archive(store, study_sha, by_id)
    by_case = defaultdict(list)
    for receipt in receipts:
        by_case[receipt["candidate_id"]].append(receipt)
    review = reconcile(study_dir, first, second) if first is not None else None
    reviewed = {r["candidate_id"]: r for r in review["candidates"]} if review else {}
    rows, statuses = [], Counter()
    for case in cases:
        cid = case["candidate_id"]
        docs = by_case[cid]
        reviewed_case = reviewed.get(cid)
        issues = []
        claim = reviewed_case["agreed_hypothesis"] if reviewed_case else None
        if reviewed_case is None:
            issues.append("independent_human_pair_reviews_not_provided")
        elif reviewed_case["review_status"] != "concordant_unverified_hypothesis":
            issues.append("reviewer_disagreement_or_inconclusive")
        if not docs:
            issues.append("no_third_party_source_bytes_archived")
        by_url = {}
        for d in docs:
            if d["source_url"] in by_url:
                issues.append("multiple_receipts_for_same_source_url")
            by_url[d["source_url"]] = d
        if reviewed_case is not None and claim is not None:
            cited = [reviewed_case["first"]["evidence_url"],
                     reviewed_case["second"]["evidence_url"]]
            if not all(u in by_url for u in cited):
                issues.append("human_review_evidence_urls_not_both_archived")
            if cited[0] == cited[1]:
                issues.append("same_document_cited_by_both_reviewers")
            for vote in ("first", "second"):
                citation = reviewed_case[vote]["evidence_url"]
                evidence = by_url.get(citation)
                if evidence is not None and _utc(evidence["captured_at"]) > _utc(
                        next(r["reviewed_at"] for r in review["reviewers"]
                             if r["reviewer_id"] == reviewed_case[vote]["reviewer_id"])):
                    issues.append("review_citation_document_archived_after_review")
        if claim is not None:
            requested = ("same_event_document_claim" if claim == "same_event_hypothesis"
                         else "different_event_document_claim")
            if any(d["relation_claim"] != requested for d in docs):
                issues.append("source_document_relation_claims_disagree")
        publishers = {d["publisher_id"].casefold() for d in docs}
        lineages = {d["upstream_family"].casefold() for d in docs}
        if len(publishers) < 2 or len(lineages) < 2:
            issues.append("two_distinct_declared_publisher_and_upstream_families_required")
        if len({d["document_sha256"] for d in docs}) < len(docs):
            issues.append("identical_archived_document_bytes_under_multiple_sources")
        if any(d["upstream_role"] != "firsthand_original_record" for d in docs):
            issues.append("secondary_or_unknown_upstream_material_requires_manual_review")
        times = [d["source_event_at"] for d in docs]
        if not docs or any(x is None for x in times):
            issues.append("source_event_time_evidence_missing")
        elif len({x[:10] for x in times}) > 1:
            issues.append("third_party_source_event_dates_disagree")
        mtbs_time = case["mtbs"]["source_ignition_at"]
        if mtbs_time is None:
            issues.append("mtbs_retrospective_event_date_missing")
        elif times and all(x is not None for x in times) and any(
                x[:4] != mtbs_time[:4] for x in times):
            issues.append("event_year_disagrees_with_mtbs_source")
        issues = sorted(set(issues))
        status = ("documentary_case_ready_for_external_adjudication_not_verified"
                  if not issues else "further_independent_evidence_required")
        statuses[status] += 1
        rows.append({
            "candidate_id": cid,
            "mtbs_fire_id": case["mtbs"]["fire_id"],
            "nifc_source_identity": case["nifc"]["source_identity"],
            "research_status": status,
            "unresolved_gates": issues,
            "document_count": len(docs),
            "archived_sources": [{
                "receipt_id": d["receipt_id"], "document_sha256": d["document_sha256"],
                "source_url": d["source_url"], "source_record_id": d["source_record_id"],
                "publisher_id": d["publisher_id"], "upstream_family": d["upstream_family"],
                "event_at": d["source_event_at"],
                "source_origin_authenticated": False,
            } for d in docs],
            "review_agreement": claim,
            "event_identity_verified": False,
            "independent_nonfire_verified": False,
        })
    return {
        "schema_version": 1,
        "status": "third_party_corroboration_structural_audit_not_ground_truth",
        "source_study_sha256": study_sha,
        "source_capture_at": study["retrieved_at"],
        "candidate_count": len(cases),
        "private_source_receipts_checked": len(receipts),
        "human_reviewer_votes_checked": review is not None,
        "statuses": {
            "documentary_case_ready_for_external_adjudication_not_verified":
                statuses["documentary_case_ready_for_external_adjudication_not_verified"],
            "further_independent_evidence_required":
                statuses["further_independent_evidence_required"],
        },
        "cases": rows,
        "verified_event_crosswalks": 0,
        "independent_nonfire_labels": 0,
        "measurement_of_forecast_accuracy": False,
        "scientific_limit": (
            "Source origin, upstream independence, incident IDs and dates are still human/operator "
            "claims; SHA-256 verifies local source preservation, never external authenticity. "
            "Even structurally complete dossiers require independent event adjudication."),
    }


HTML_STYLE = """
:root{font-family:system-ui,sans-serif;color-scheme:light;background:#f2f5f6;color:#182f39}
body{max-width:1150px;margin:auto;padding:20px;line-height:1.5}
header,main,footer{background:white;padding:20px;border:1px solid #ced9dd;border-radius:9px;margin:12px 0}
h1{font-size:1.6rem}h2{font-size:1.15rem}
table{border-collapse:collapse;width:100%}th,td{padding:9px;text-align:left;border-bottom:1px solid #d4dde1}
th{background:#edf1f2}td{overflow-wrap:anywhere}
small{color:#415b65}.warning{color:#875113}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}
@media(max-width:750px){body{padding:8px}header,main,footer{padding:12px}
thead{display:none}table,tr,td,tbody{display:block}tr{border-bottom:2px solid #8aa0a9}
td{border:0;padding:5px}td:before{content:attr(data-label) ": ";font-weight:700}}
"""


def render_audit(report: dict) -> str:
    if (report.get("status") != "third_party_corroboration_structural_audit_not_ground_truth"
            or report.get("verified_event_crosswalks") != 0 or
            report.get("independent_nonfire_labels") != 0):
        raise ValueError("external evidence report is not a scientifically guarded structural audit")
    e = lambda x: html.escape(str(x), quote=True)
    rows = []
    for case in report["cases"]:
        sources = "".join(
            "<li>Publisher declaration: " + e(src["publisher_id"]) +
            "; upstream: " + e(src["upstream_family"]) +
            "; source ID: " + e(src["source_record_id"]) +
            "; archived document SHA-256: " + e(src["document_sha256"]) +
            "; cited HTTPS URL: " + e(src["source_url"]) + "</li>"
            for src in case["archived_sources"])
        details = ("<details><summary>Source claims and remaining gates</summary><ul>" +
                   sources + "</ul><p>" + e(", ".join(case["unresolved_gates"]) or
                   "No remaining structural gaps; independent adjudication STILL required.") +
                   "</p></details>")
        values = [
            ("Candidate", case["candidate_id"]),
            ("State", case["research_status"]),
            ("Archived sources", case["document_count"]),
            ("Reviewer hypothesis", case["review_agreement"] or "not completed"),
        ]
        cells = "".join('<td data-label="' + e(label) + '">' + e(value) + "</td>"
                        for label, value in values)
        rows.append("<tr>" + cells + "<td data-label=\"Review gates\">" + details + "</td></tr>")
    css_sha = base64.b64encode(hashlib.sha256(HTML_STYLE.encode()).digest()).decode()
    csp = ("default-src 'none'; connect-src 'none'; script-src 'none'; img-src 'none'; "
           "object-src 'none'; base-uri 'none'; style-src 'sha256-" + css_sha + "'")
    counts = report["statuses"]
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="' + e(csp) + '">'
        '<title>Private third-party incident evidence audit</title><style>' + HTML_STYLE +
        '</style></head><body><header><h1>Independent-event evidence dossiers</h1>'
        '<p>Original research source SHA-256: ' + e(report["source_study_sha256"]) + '</p>'
        '<p class="warning">All source origins, upstream families and cross-references '
        'remain operator-supplied claims. No verified event identities or nonfire labels.</p>'
        '</header><main><h2>Independent adjudication readiness (not verification)</h2>'
        '<p>Structurally ready: ' +
        str(counts["documentary_case_ready_for_external_adjudication_not_verified"]) +
        ' · Missing evidence/review: ' + str(counts["further_independent_evidence_required"]) +
        '</p><table><thead><tr><th>Candidate</th><th>State</th><th>Archived sources</th>'
        '<th>Reviewer hypothesis</th><th>Review gates</th></tr></thead><tbody>' +
        "".join(rows) + '</tbody></table></main>'
        '<footer><small>Private offline audit only; original document integrity is not '
        'publisher authentication or independent wildfire occurrence validation.</small></footer>'
        '</body></html>\n'
    )


def _write(path: Path, value: dict) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("new output required, do not overwrite private evidence")
    encoded = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if len(encoded.encode()) > MAX_REPORT:
        raise ValueError("casebook output exceeds private report budget")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        f.write(encoded)


def main() -> None:
    parser = argparse.ArgumentParser(description="Private independent-event evidence dossiers; not wildfire labels")
    commands = parser.add_subparsers(dest="action", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--study-dir", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    cp = commands.add_parser("capture")
    cp.add_argument("--study-dir", type=Path, required=True)
    cp.add_argument("--store", type=Path, required=True)
    cp.add_argument("--metadata", type=Path, required=True)
    cp.add_argument("--document", type=Path, required=True)
    check = commands.add_parser("audit")
    check.add_argument("--study-dir", type=Path, required=True)
    check.add_argument("--store", type=Path, required=True)
    check.add_argument("--first", type=Path)
    check.add_argument("--second", type=Path)
    check.add_argument("--output", type=Path, required=True)
    check.add_argument("--html", type=Path, help="Optional private offline read-only evidence audit HTML")
    args = parser.parse_args()
    if args.action == "prepare":
        if args.output.resolve().is_relative_to(args.study_dir.resolve()):
            parser.error("casebook output must be outside original government source archive")
        _write(args.output, prepare(args.study_dir))
    elif args.action == "capture":
        result = capture(args.study_dir, args.store, args.metadata, args.document)
        print(json.dumps({"case_id": result["candidate_id"], "receipt_id": result["receipt_id"],
                          "source_origin_authenticated": False}, sort_keys=True))
    else:
        if (args.output.resolve().is_relative_to(args.study_dir.resolve()) or
                args.output.resolve().is_relative_to(args.store.resolve()) or
                args.output.resolve() in {p.resolve() for p in (args.first, args.second) if p}):
            parser.error("audit output must be separate from original/private evidence")
        if (args.html is not None and
                (args.html.resolve() == args.output.resolve() or
                 args.html.exists() or args.html.resolve().is_relative_to(args.study_dir.resolve()) or
                 args.html.resolve().is_relative_to(args.store.resolve()) or
                 args.html.resolve() in {p.resolve() for p in (args.first, args.second) if p})):
            parser.error("private HTML output must be new, distinct and outside source archives/votes")
        result = audit(args.study_dir, args.store, args.first, args.second)
        html_output = render_audit(result) if args.html is not None else None
        _write(args.output, result)
        if args.html is not None:
            try:
                args.html.parent.mkdir(parents=True, exist_ok=True)
                with args.html.open("x", encoding="utf-8") as target:
                    target.write(html_output)
            except BaseException:
                args.output.unlink()
                raise
        print(json.dumps({"candidate_count": result["candidate_count"],
                          "cases_needing_evidence": result["statuses"]["further_independent_evidence_required"],
                          "verified_event_crosswalks": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
