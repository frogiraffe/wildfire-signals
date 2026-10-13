"""Offline blind review of original CAL FIRE alternative-page hypotheses.

Reviewer agreement is a *research hypothesis*, never a fire identity, wildfire
presence/absence label, source-independence proof, or forecast validation.
The CLI replays original NIFC/MTBS/CAL FIRE bytes on every invocation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import html
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .calfire_ambiguity_dossiers import investigate

MAX_BYTES = 2 * 1024 * 1024
RESEARCH_STATUS = "candidate_alternative_event_dossiers_not_independent_event_identity"
CHOICES = ("prefer_source_lead", "unresolved")
LINEAGE = ("unknown", "shared_upstream", "potentially_independent_not_verified")


def _json(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def _digest(value: dict) -> str:
    return hashlib.sha256(_json(value)).hexdigest()


def _text(value: object, name: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= 1024:
        raise ValueError(f"{name} must be nonempty bounded text")
    return value.strip()


def _https(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        p = urlsplit(value)
        return (p.scheme == "https" and bool(p.hostname) and
                not p.username and not p.password and
                all(ord(c) >= 32 for c in value) and "\\" not in value)
    except ValueError:
        return False


def _original_cases(report: dict) -> dict[str, dict]:
    if (report.get("schema_version") != 1 or
            report.get("research_status") != RESEARCH_STATUS or
            report.get("validated_same_fire_event_crosswalks") != 0 or
            report.get("independent_nonfire_observations") != 0 or
            report.get("measured_wildfire_forecast_skill") is not False or
            report.get("calfire_details_covers_only_name_linked_subset_not_all_historical_fires") is not True):
        raise ValueError("complete unverified original-source ambiguity dossier required")
    rows = report.get("cases")
    if (not isinstance(rows, list) or not 1 <= len(rows) <= 400 or
            report.get("research_candidate_count") != len(rows)):
        raise ValueError("source candidate population incomplete")
    cases = {}
    urls = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid source case")
        cid = _text(row.get("candidate_id"), "candidate ID")
        if cid in cases or row.get("event_identity_verified") is not False or row.get("fire_absence_verified") is not False:
            raise ValueError("duplicate candidate or invalid source truth")
        options = row.get("official_calfire_page_options")
        if not isinstance(options, list) or len(options) != row.get("source_option_count"):
            raise ValueError("source option drift")
        seen = set()
        for option in options:
            url = option.get("source_url")
            sha = option.get("source_detail_html_sha256")
            if (not _https(url) or url in seen or not isinstance(sha, str) or
                    len(sha) != 64 or any(ch not in "0123456789abcdef" for ch in sha) or
                    option.get("verified_event_identity") is not False):
                raise ValueError("unverified source page URL/SHA required")
            seen.add(url)
            urls.add(url)
        cases[cid] = row
    if len(urls) != report.get("candidate_linked_unique_pages_verified"):
        raise ValueError("archived original source URL population drift")
    if (report.get("candidate_linked_unique_pages_verified") !=
            report.get("candidate_linked_original_pages_verified")):
        raise ValueError("original detail page coverage incomplete")
    return {cid: row for cid, row in sorted(cases.items())
            if row["source_option_count"] > 1}


def _template(report: dict, reviewer_id: str) -> dict:
    reviewer = _text(reviewer_id, "reviewer identity")
    cases = _original_cases(report)
    return {
        "schema_version": 1,
        "research_status": "blind_source_lead_hypotheses_only",
        "casebook_sha256": _digest(report),
        "reviewer_id": reviewer,
        "votes": [{
            "candidate_id": cid, "decision": "unresolved",
            "selected_source_url": None, "source_lineage": "unknown",
            "external_evidence_url": None, "reason": "",
            "reviewed_at": None,
        } for cid in cases],
    }


def packet(report: dict, reviewer_id: str) -> tuple[str, dict]:
    """Read-only self-contained HTML, separately filled JSON; never show peer votes."""
    template = _template(report, reviewer_id)
    cases = _original_cases(report)
    e = lambda v: html.escape(str(v), quote=True)
    sections = []
    for cid, row in cases.items():
        links = []
        for option in row["official_calfire_page_options"]:
            links.append(
                '<li><a rel="noopener noreferrer" href="' + e(option["source_url"]) +
                '">' + e(option["source_name"]) + '</a> · ' +
                'original SHA-256 ' + e(option["source_detail_html_sha256"]) +
                ' · date ' + e(option["source_start_day"]) +
                ' · retrospective MTBS day gap ' +
                e(option["mtbs_start_day_gap_abs"]) + '</li>')
        sections.append('<section><h2>' + e(cid) + '</h2><p>MTBS ' +
                        e(row["mtbs_fire_id"]) + ' · NIFC ' +
                        e(row["nifc_source_identity"]) + '</p><ul>' +
                        "".join(links) + '</ul><p>Unresolved: ' +
                        e(", ".join(row["unresolved_evidence_gates"])) + '</p></section>')
    css = ("body{font:1rem/1.5 system-ui;max-width:65rem;margin:1rem auto;padding:1rem}"
           "section{border-top:1px solid #aaa;padding:1rem 0}"
           "code,li{overflow-wrap:anywhere}.warning{font-weight:600}")
    csp_sha = __import__("base64").b64encode(hashlib.sha256(css.encode()).digest()).decode()
    csp = ("default-src 'none'; script-src 'none'; connect-src 'none'; "
           "img-src 'none'; object-src 'none'; base-uri 'none'; "
           "style-src 'sha256-" + csp_sha + "'")
    page = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="' + e(csp) + '">'
            '<title>Independent CAL FIRE source-lead review</title><style>' + css +
            '</style></head><body><h1>Independent historical source-lead review</h1>'
            '<p>Reviewer ' + e(reviewer_id) + ' · casebook SHA-256 <code>' +
            template["casebook_sha256"] + '</code></p>'
            '<p class="warning">No event identity is verified. A name match, '
            'location or agreement is not independent evidence. Do not infer fire '
            'absence from an unlinked CAL FIRE page.</p>' + "".join(sections) +
            '</body></html>\n')
    return page, template


def _read_votes(report: dict, raw: dict) -> tuple[str, dict[str, dict]]:
    cases = _original_cases(report)
    if (not isinstance(raw, dict) or raw.get("schema_version") != 1 or
            raw.get("research_status") != "blind_source_lead_hypotheses_only" or
            raw.get("casebook_sha256") != _digest(report)):
        raise ValueError("review votes not bound to exact original-source casebook")
    reviewer = _text(raw.get("reviewer_id"), "reviewer identity")
    votes = raw.get("votes")
    if not isinstance(votes, list) or len(votes) != len(cases):
        raise ValueError("one explicit vote for every ambiguous case required")
    by_id = {}
    allowed = {"candidate_id", "decision", "selected_source_url",
               "source_lineage", "external_evidence_url", "reason", "reviewed_at"}
    for vote in votes:
        if not isinstance(vote, dict) or set(vote) != allowed:
            raise ValueError("unknown or omitted reviewer vote fields")
        cid = _text(vote["candidate_id"], "candidate ID")
        if cid not in cases or cid in by_id:
            raise ValueError("unknown or duplicate candidate vote")
        if vote["decision"] not in CHOICES or vote["source_lineage"] not in LINEAGE:
            raise ValueError("unknown source-lead research decision")
        _text(vote["reason"], "review reason", 12)
        stamp = vote["reviewed_at"]
        if not isinstance(stamp, str):
            raise ValueError("review timestamp required")
        try:
            parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid review timestamp") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("review timestamp must have explicit UTC offset")
        selection = vote["selected_source_url"]
        cited = vote["external_evidence_url"]
        if vote["decision"] == "prefer_source_lead":
            valid = {o["source_url"] for o in cases[cid]["official_calfire_page_options"]}
            if selection not in valid or not _https(cited):
                raise ValueError("preferred lead requires an original official URL and HTTPS evidence")
        elif (selection is not None or cited is not None or vote["source_lineage"] != "unknown"):
            raise ValueError("unresolved vote must not assert an event link or source independence")
        by_id[cid] = vote
    return reviewer, by_id


def reconcile(report: dict, first: dict, second: dict) -> dict:
    """Retain both independent inputs, disagreements, and shared-page collisions."""
    reviewer_a, votes_a = _read_votes(report, first)
    reviewer_b, votes_b = _read_votes(report, second)
    if reviewer_a.casefold() == reviewer_b.casefold() or _digest(first) == _digest(second):
        raise ValueError("two distinct reviewer identities and vote files required")
    cases = _original_cases(report)
    statuses = Counter()
    selected_by = {}
    rows = []
    for cid, case in cases.items():
        a, b = votes_a[cid], votes_b[cid]
        if a["decision"] == b["decision"] == "prefer_source_lead":
            status = ("concordant_unverified_lead" if
                      a["selected_source_url"] == b["selected_source_url"]
                      else "conflicting_source_leads")
        elif a["decision"] == b["decision"] == "unresolved":
            status = "both_unresolved"
        else:
            status = "partially_unresolved"
        agreed = a["selected_source_url"] if status == "concordant_unverified_lead" else None
        if agreed:
            selected_by.setdefault(agreed, []).append(cid)
        flags = ["source_independence_not_authenticated", "not_ground_truth"]
        if any(v["source_lineage"] == "shared_upstream" for v in (a, b)):
            flags.append("reviewer_reports_common_upstream_source")
        if a["external_evidence_url"] and a["external_evidence_url"] == b["external_evidence_url"]:
            flags.append("same_evidence_url_not_independent_corroboration")
        if status != "concordant_unverified_lead":
            flags.append("unresolved_or_conflicting_independent_review")
        if agreed and any(o["source_url"] == agreed and
                          o["candidate_pair_count_reusing_url"] > 1
                          for o in case["official_calfire_page_options"]):
            flags.append("official_incident_page_reused_by_multiple_candidates")
        statuses[status] += 1
        rows.append({
            "candidate_id": cid, "status": status, "agreed_lead_hypothesis": agreed,
            "first": dict(a, reviewer_id=reviewer_a),
            "second": dict(b, reviewer_id=reviewer_b),
            "research_flags": flags,
            "same_physical_fire_verified": False,
            "independent_wildfire_outcome_verified": False,
            "verified_nonfire": False,
        })
    for row in rows:
        lead = row["agreed_lead_hypothesis"]
        if lead is not None and len(selected_by[lead]) > 1:
            row["research_flags"].append("multiple_candidate_pairs_select_same_incident_page")
    return {
        "schema_version": 1,
        "research_status": "two_independent_hypotheses_not_adjudicated_fire_identities",
        "source_casebook_sha256": _digest(report),
        "original_nifc_mtbs_study_sha256": report["nifc_mtbs_original_study_sha256"],
        "original_calfire_annual_html_sha256": report["calfire_original_annual_archive_sha256"],
        "reviewer_inputs": [
            {"reviewer_id": reviewer_a, "vote_json_sha256": _digest(first)},
            {"reviewer_id": reviewer_b, "vote_json_sha256": _digest(second)},
        ],
        "ambiguous_candidates_reviewed": len(rows),
        "dispositions": {k: statuses[k] for k in (
            "concordant_unverified_lead", "conflicting_source_leads",
            "partially_unresolved", "both_unresolved")},
        "cases": rows,
        "verified_same_fire_event_crosswalks": 0,
        "verified_nonfire_labels": 0,
        "forecast_skill_measured": False,
    }


def _load_votes(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("missing, symbolic or oversized private vote file")
    try:
        return json.loads(path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("invalid private vote JSON") from exc


def _write_new(destination: Path, data: dict[str, bytes], sources: list[Path]) -> None:
    resolved = destination.resolve()
    if (destination.exists() or destination.is_symlink() or
            any(resolved.is_relative_to(p.resolve()) or
                p.resolve().is_relative_to(resolved) for p in sources)):
        raise ValueError("new private output directory must not overlap any source or vote inputs")
    if any(len(value) > MAX_BYTES for value in data.values()):
        raise ValueError("private review output exceeds safe size limit")
    destination.mkdir(parents=True, mode=0o700)
    written = []
    try:
        for name, value in data.items():
            target = destination / name
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            written.append(target)
            with os.fdopen(fd, "wb") as handle:
                handle.write(value)
    except BaseException:
        for p in written:
            p.unlink(missing_ok=True)
        destination.rmdir()
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Blind CAL FIRE source-lead review; no verified wildfire labels")
    parser.add_argument("command", choices=("packet", "reconcile"))
    parser.add_argument("--study-dir", type=Path, required=True)
    parser.add_argument("--calfire-archive-dir", type=Path, required=True)
    parser.add_argument("--batch", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reviewer-id")
    parser.add_argument("--first", type=Path)
    parser.add_argument("--second", type=Path)
    args = parser.parse_args()
    original = [args.study_dir, args.calfire_archive_dir, *args.batch]
    report = investigate(args.study_dir, args.calfire_archive_dir, args.batch)
    if args.command == "packet":
        if not args.reviewer_id or args.first or args.second:
            parser.error("packet needs --reviewer-id only")
        page, votes = packet(report, args.reviewer_id)
        data = {"independent-packet.html": page.encode("utf-8"),
                "private-vote-template.json": _json(votes)}
    else:
        if not args.first or not args.second or args.reviewer_id:
            parser.error("reconcile needs --first and --second only")
        if args.first.resolve() == args.second.resolve():
            parser.error("two distinct files required")
        result = reconcile(report, _load_votes(args.first), _load_votes(args.second))
        data = {"research-reconciliation.json": _json(result)}
        original += [args.first, args.second]
    _write_new(args.output_dir, data, original)
    print(json.dumps({"written": sorted(data), "ambiguous_cases": len(_original_cases(report)),
                      "verified_event_identities": 0, "verified_nonfire": 0}))


if __name__ == "__main__":
    main()
