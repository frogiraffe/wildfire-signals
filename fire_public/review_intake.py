"""Blind offline review packets and auditable two-reviewer vote reconciliation.

The packet contains source leads, never another reviewer's votes. Reconciliation
preserves disagreements as unresolved and delegates all label safety checks to
the existing label_review validator. External evidence remains human-attested.
"""
from __future__ import annotations

import argparse
import html
import json
from collections import Counter
from pathlib import Path

from .label_review import (
    MAX_FRAME_BYTES, MAX_REVIEW_BYTES, _load, _review_decision, _sha, _text,
    _url, _utc, _write_new,
)
from .labeled_evaluation import _manifest


def _queue(path: Path) -> tuple[dict, dict[str, dict], str]:
    q = _load(path, MAX_REVIEW_BYTES)
    cases = q.get("cases")
    if (q.get("schema_version") != 1 or q.get("state") != "unadjudicated_review_queue"
            or not isinstance(cases, list) or not 1 <= len(cases) <= 400):
        raise ValueError("valid unadjudicated review queue required")
    by_id = {}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("queue case must be an object")
        identity = _text(case.get("case_id"), "queue case identity")
        if identity in by_id:
            raise ValueError("duplicate queue case identity")
        if case.get("kind") not in (
                "retrospective_official_perimeter_review", "independent_frame_review"):
            raise ValueError("unknown queue case kind")
        by_id[identity] = case
    return q, by_id, _sha(path)


def packet(queue_path: Path, reviewer_id: str) -> tuple[str, dict]:
    """Return a self-contained read-only HTML brief and empty private vote form."""
    q, cases, digest = _queue(queue_path)
    reviewer = _text(reviewer_id, "reviewer identity")
    e = lambda value: html.escape(str(value), quote=True)
    sections = []
    for case in cases.values():
        if case["kind"] == "retrospective_official_perimeter_review":
            context = (f"NIFC retrospective lead; fire year {e(case.get('source_fire_year'))}; "
                       f"ObjectID {e(case.get('source_object_id'))}; "
                       f"name {e(case.get('source_name') or 'unavailable')}. "
                       "The fire year is not an ignition date or historical feature receipt.")
        else:
            context = (f"Independent frame unit {e(case.get('sampling_unit_id'))}; "
                       f"region {e(case.get('region_id'))}; "
                       f"point {e(case.get('latitude'))}, {e(case.get('longitude'))}; "
                       f"decision {e(case.get('decision_at'))}. "
                       "This unit is not presumed fire-free.")
        sections.append(f"<section><h2>{e(case['case_id'])}</h2><p>{context}</p></section>")
    links = []
    for label, url in (("NIFC source", q.get("official_source")),
                       ("Sampling frame", q.get("sampling_frame", {}).get("source"))):
        if _url(url):
            links.append(f'<a href="{e(url)}" rel="noopener noreferrer">{e(label)}</a>')
    page = ("<!doctype html><html lang=\"en\"><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            "<title>Independent wildfire review packet</title>"
            "<style>body{font:1rem/1.5 system-ui;max-width:48rem;margin:2rem auto;padding:0 1rem}"
            "section{border-top:1px solid #aaa;padding:1rem 0}code{overflow-wrap:anywhere}</style>"
            f"<h1>Independent review packet</h1><p>Reviewer: {e(reviewer)}</p>"
            f"<p>Queue SHA-256: <code>{digest}</code></p>"
            "<p>All cases are unlabeled. Inspect independent evidence and complete "
            "the separate vote JSON without seeing another reviewer's decisions. "
            "A source URL or name alone does not prove a wildfire or no-fire outcome.</p>"
            + "<p>Sources: " + ", ".join(links) + "</p>"
            + "".join(sections) + "</html>\n")
    template = {"schema_version": 1, "queue_sha256": digest,
                "reviewer_id": reviewer, "votes": [
                    {"case_id": case_id, "status": "unreviewed",
                     "reviewer_label": None, "independent_evidence_checked": False,
                     "evidence_url": None, "reviewed_at": None}
                    for case_id in cases]}
    return page, template


def details_template(queue_path: Path) -> dict:
    """Give a coordinator case identities and known frame times without labels."""
    _, cases, digest = _queue(queue_path)
    entries = []
    for case_id, case in cases.items():
        entry = {"case_id": case_id,
                 "event_id": None,
                 "region_id": case.get("region_id"),
                 "decision_at": case.get("decision_at"),
                 "feature_cutoff_at": None,
                 "label_available_at": None,
                 "label_verified_at": None,
                 "label_source": None,
                 "label_source_id": None,
                 "label_evidence_url": None,
                 "independently_verified_event_at": None,
                 "negative_coverage": None}
        entries.append(entry)
    return {"schema_version": 1, "queue_sha256": digest, "cases": entries}


def _votes(path: Path, case_ids: set[str], digest: str) -> tuple[str, dict[str, dict]]:
    source = _load(path, MAX_REVIEW_BYTES)
    if source.get("schema_version") != 1 or source.get("queue_sha256") != digest:
        raise ValueError("reviewer vote queue SHA does not match exact source queue")
    reviewer = _text(source.get("reviewer_id"), "reviewer identity")
    records = source.get("votes")
    if not isinstance(records, list) or len(records) != len(case_ids):
        raise ValueError("reviewer must address every queued case")
    out = {}
    for vote in records:
        if not isinstance(vote, dict):
            raise ValueError("review vote must be an object")
        allowed = {"case_id", "status", "reviewer_label", "independent_evidence_checked",
                   "evidence_url", "reviewed_at", "reason"}
        if set(vote) - allowed:
            raise ValueError("unexpected vote fields cannot override reviewer identity")
        case_id = _text(vote.get("case_id"), "vote case identity")
        if case_id in out:
            raise ValueError("duplicate reviewer vote")
        status = vote.get("status")
        if status == "abstain":
            _text(vote.get("reason"), "abstention reason", 8)
        elif status == "vote":
            if (type(vote.get("reviewer_label")) is not int
                    or vote["reviewer_label"] not in (0, 1)
                    or vote.get("independent_evidence_checked") is not True
                    or not _url(vote.get("evidence_url"))):
                raise ValueError("vote requires independent evidence, URL and binary label")
            _utc(_text(vote.get("reviewed_at"), "vote review timestamp"))
        else:
            raise ValueError("all reviewer cases must be voted or explicitly abstained")
        out[case_id] = vote
    if set(out) != case_ids:
        raise ValueError("reviewer must address every queued case")
    return reviewer, out


def reconcile(queue_path: Path, first_path: Path, second_path: Path,
              details_path: Path, protocol_path: Path) -> tuple[dict, dict]:
    """Build finalize-compatible reviews; never adjudicate a disagreement."""
    q, cases, digest = _queue(queue_path)
    first_id, first = _votes(first_path, set(cases), digest)
    second_id, second = _votes(second_path, set(cases), digest)
    if first_id == second_id or first_path.resolve() == second_path.resolve():
        raise ValueError("two distinct reviewers and vote files required")
    details = _load(details_path, MAX_REVIEW_BYTES)
    if details.get("schema_version") != 1 or details.get("queue_sha256") != digest:
        raise ValueError("coordinator details queue SHA does not match source queue")
    provided = details.get("cases")
    if not isinstance(provided, list):
        raise ValueError("coordinator case details list required")
    by_detail = {}
    for item in provided:
        if not isinstance(item, dict):
            raise ValueError("coordinator case details must be objects")
        case_id = _text(item.get("case_id"), "coordinator case identity")
        if case_id in by_detail or case_id not in cases:
            raise ValueError("duplicate or unknown coordinator case identity")
        if any(key in item for key in ("label", "status", "primary", "secondary",
                                       "reviewer_votes")):
            raise ValueError("coordinator may not overwrite independent vote fields")
        by_detail[case_id] = item
    protocol = _load(protocol_path, MAX_FRAME_BYTES)
    _manifest(protocol)
    horizon = float(protocol["horizon_hours"])
    decisions = []
    counts = Counter()
    conflicts = []
    for case_id, case in cases.items():
        a, b = first[case_id], second[case_id]
        audit = [{"reviewer_id": first_id, **a}, {"reviewer_id": second_id, **b}]
        if (a["status"] != "vote" or b["status"] != "vote"
                or a["reviewer_label"] != b["reviewer_label"]):
            reason = ("Independent reviewer labels conflict" if
                      a["status"] == b["status"] == "vote" else
                      "At least one independent reviewer abstained")
            decisions.append({"case_id": case_id, "status": "unresolved",
                              "reason": reason, "reviewer_votes": audit})
            counts["conflicted" if a["status"] == b["status"] == "vote"
                   else "abstained"] += 1
            if a["status"] == b["status"] == "vote":
                conflicts.append(case_id)
            continue
        if case_id not in by_detail:
            raise ValueError(f"coordinator details required for matched case {case_id}")
        label = a["reviewer_label"]
        entry = dict(by_detail[case_id])
        entry.update({"case_id": case_id, "status": "adjudicated", "label": label,
                      "primary": {"reviewer_id": first_id, "agrees_with_label": True,
                                  **{k:v for k,v in a.items() if k not in ("case_id","status")}},
                      "secondary": {"reviewer_id": second_id, "agrees_with_label": True,
                                    **{k:v for k,v in b.items() if k not in ("case_id","status")}}})
        _review_decision(case, entry, horizon)
        decisions.append(entry)
        counts["matched"] += 1
    reviews = {"schema_version": 1, "queue_sha256": digest,
               "vote_file_sha256": [_sha(first_path), _sha(second_path)],
               "coordinator_details_sha256": _sha(details_path),
               "decisions": decisions}
    report = {"schema_version": 1, "queue_sha256": digest,
              "matched": counts["matched"], "conflicted": counts["conflicted"],
              "abstained": counts["abstained"],
              "conflicted_case_ids": conflicts,
              "note": "Matched votes passed structural review only; external evidence and reviewer independence require human audit."}
    return reviews, report


def main() -> None:
    parser = argparse.ArgumentParser(description="Blind private wildfire label review intake")
    sub = parser.add_subparsers(dest="command", required=True)
    brief = sub.add_parser("packet", help="Create a private blind HTML packet and vote template")
    brief.add_argument("--queue", required=True, type=Path)
    brief.add_argument("--reviewer-id", required=True)
    brief.add_argument("--html", required=True, type=Path)
    brief.add_argument("--vote-template", required=True, type=Path)
    coordinator = sub.add_parser("details-template", help="Create an unlabeled coordinator case form")
    coordinator.add_argument("--queue", required=True, type=Path)
    coordinator.add_argument("--output", required=True, type=Path)
    join = sub.add_parser("reconcile", help="Combine separate votes without resolving conflicts")
    for key in ("queue", "first", "second", "details", "protocol", "reviews", "report"):
        join.add_argument("--"+key, required=True, type=Path)
    args = parser.parse_args()
    if args.command == "packet":
        outputs = [args.html, args.vote_template]
        inputs = [args.queue]
        page, form = packet(args.queue, args.reviewer_id)
        contents = [page, json.dumps(form, indent=2, ensure_ascii=False)+"\n"]
    elif args.command == "details-template":
        outputs = [args.output]
        inputs = [args.queue]
        contents = [json.dumps(details_template(args.queue), indent=2, ensure_ascii=False)+"\n"]
    else:
        outputs = [args.reviews, args.report]
        inputs = [args.queue, args.first, args.second, args.details, args.protocol]
        reviews, report = reconcile(*inputs)
        contents = [json.dumps(value, indent=2, ensure_ascii=False)+"\n"
                    for value in (reviews, report)]
    if (len({p.resolve() for p in outputs}) != len(outputs)
            or any(p.resolve() in {x.resolve() for x in inputs} or p.exists()
                   for p in outputs)):
        parser.error("outputs must be new, distinct, and must not overwrite inputs")
    created = []
    try:
        for path, content in zip(outputs, contents):
            _write_new(path, content)
            created.append(path)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    print(json.dumps({"outputs": [str(p) for p in outputs]}, sort_keys=True))


if __name__ == "__main__":
    main()
