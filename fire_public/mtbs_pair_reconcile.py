"""Source-bound two-reviewer reconciliation of MTBS–NIFC pair hypotheses.

All agreement is agreement between *opinions*, not proof that a fire event,
nonfire event, ignition date or independent observation has been verified.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime
import hashlib
import html
import json
from pathlib import Path
from urllib.parse import urlsplit

from .label_review import _utc
from .mtbs_match_review import (
    _bounded_file, _sha, load_study, validate_votes, MAX_VOTES_BYTES,
)

MAX_OUTPUT_BYTES = 1024 * 1024

STYLE = """
:root{font-family:system-ui,sans-serif;color-scheme:light;background:#f2f5f6;color:#1b333a}
body{max-width:1170px;margin:0 auto;padding:20px;line-height:1.5}
header,main,footer{background:white;border:1px solid #c9d3d8;padding:18px;
border-radius:10px;margin:12px 0}
h1{font-size:1.7rem}h2{font-size:1.18rem}h3{font-size:1rem}
table{width:100%;border-collapse:collapse;font-size:.94rem}td,th{padding:12px;
border-bottom:1px solid #d7e0e3;text-align:left;vertical-align:top}
code,td{overflow-wrap:anywhere}a{color:#175978}
small{color:#465c64}.notice{color:#6e460c}
.summary{display:flex;gap:18px;flex-wrap:wrap;margin:14px 0}
.summary strong{font-size:1.45rem;display:block}tr:target{outline:3px solid #9e792f}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}
@media(max-width:740px){body{padding:8px}header,main,footer{padding:10px}
table,tbody,thead,tr,td,th{display:block}thead{display:none}tr{border-bottom:2px solid #7f9ca4}
td{border:0;padding:4px 8px}td:before{content:attr(data-label) ": ";font-weight:700}}
"""


def _canonical(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False)+"\n").encode()


def _vote_map(path: Path, cases: list[dict]) -> dict[str, dict]:
    raw=_bounded_file(path,MAX_VOTES_BYTES)
    values=json.loads(raw)
    by_id={row["candidate_id"]:row for row in cases}
    votes=values["votes"]
    # Both count and set identity are validated by mtbs_match_review.validate_votes.
    return {vote["candidate_id"]:vote for vote in votes}


def _evidence_group(url1: str | None, url2: str | None) -> str:
    if url1 and url2:
        return "same_cited_url_not_independent_sources" if url1==url2 else "different_cited_urls_not_source_independence"
    return "one_or_both_sources_not_cited"


def reconcile(study_dir: Path, first_path: Path, second_path: Path) -> dict:
    if first_path.resolve()==second_path.resolve():
        raise ValueError("each independent reviewer must supply a different vote file")
    if (first_path.resolve().is_relative_to(study_dir.resolve()) or
            second_path.resolve().is_relative_to(study_dir.resolve())):
        raise ValueError("private reviewer votes cannot be stored in public research source directory")
    a_summary=validate_votes(study_dir,first_path)
    b_summary=validate_votes(study_dir,second_path)
    a_name,b_name=a_summary["reviewer_id"],b_summary["reviewer_id"]
    if a_name.casefold()==b_name.casefold():
        raise ValueError("two distinct reviewer identities required")
    study,digest,cases=load_study(study_dir)
    if a_summary["source_bundle_sha256"]!=digest or b_summary["source_bundle_sha256"]!=digest:
        raise ValueError("reviewer votes not from the same original provider study")
    a_raw=json.loads(_bounded_file(first_path,MAX_VOTES_BYTES))
    b_raw=json.loads(_bounded_file(second_path,MAX_VOTES_BYTES))
    a_votes=_vote_map(first_path,cases)
    b_votes=_vote_map(second_path,cases)
    reviewers=[
        {"reviewer_id":a_name,"vote_sha256":a_summary["review_sha256"],
         "reviewed_at":a_raw["reviewed_at"],"role":"first_blind_review"},
        {"reviewer_id":b_name,"vote_sha256":b_summary["review_sha256"],
         "reviewed_at":b_raw["reviewed_at"],"role":"second_blind_review"},
    ]
    for r in reviewers:
        if _utc(r["reviewed_at"])<_utc(study["retrieved_at"]):
            raise ValueError("review timestamp predates original source study capture")
    mtbs_counter=Counter(c["mtbs"]["object_id"] for c in cases)
    nifc_counter=Counter(c["nifc"]["object_id"] for c in cases)
    rows=[]
    summary=Counter()
    citations=Counter()
    for case in cases:
        cid=case["candidate_id"]
        left,right=a_votes[cid],b_votes[cid]
        x,y=left["decision"],right["decision"]
        if x==y and x!="inconclusive":
            status="concordant_unverified_hypothesis"
        elif x==y:
            status="both_inconclusive"
        elif "inconclusive" in (x,y):
            status="partially_inconclusive"
        else:
            status="conflicting_hypotheses"
        evidence=_evidence_group(left["evidence_url"],right["evidence_url"])
        summary[status]+=1
        citations[evidence]+=1
        flags=[]
        if case["mtbs"]["fire_type"] is None or (
                "wildfire" not in str(case["mtbs"]["fire_type"]).casefold()):
            flags.append("mtbs_fire_type_not_explicitly_wildfire")
        if case["mtbs"]["source_ignition_at"] is None:
            flags.append("retrospective_mtbs_ignition_date_missing")
        if mtbs_counter[case["mtbs"]["object_id"]]>1 or nifc_counter[case["nifc"]["object_id"]]>1:
            flags.append("many_to_many_geographic_candidates_no_unique_matching")
        if evidence=="same_cited_url_not_independent_sources":
            flags.append("reviewers_cited_same_url_no_source_independence")
        if status!="concordant_unverified_hypothesis":
            flags.append("disagreement_or_inconclusive_requires_coordinator_review")
        rows.append({
            "candidate_id":cid,"review_status":status,
            "agreed_hypothesis":x if status=="concordant_unverified_hypothesis" else None,
            "nifc":{"object_id":case["nifc"]["object_id"],
                    "name":case["nifc"]["name"],
                    "source_identity":case["nifc"]["source_identity"]},
            "mtbs":{"object_id":case["mtbs"]["object_id"],
                    "source_fire_id":case["mtbs"]["fire_id"],
                    "name":case["mtbs"]["name"],
                    "fire_type":case["mtbs"]["fire_type"],
                    "retrospective_source_ignition_at":case["mtbs"]["source_ignition_at"]},
            "first":{"reviewer_id":a_name,"decision":x,
                     "reason":left["reason"],"evidence_url":left["evidence_url"]},
            "second":{"reviewer_id":b_name,"decision":y,
                      "reason":right["reason"],"evidence_url":right["evidence_url"]},
            "cited_evidence_relation":evidence,
            "human_follow_up_flags":flags,
            "fire_event_identity_verified":False,
            "independent_fire_outcome_verified":False,
            "fire_absence_verified":False,
        })
    rows.sort(key=lambda x:x["candidate_id"])
    result={
        "schema_version":1,
        "research_status":"two_blind_reviewer_hypotheses_not_event_adjudication",
        "source_study_sha256":digest,
        "source_region_wgs84_bbox":study["roi_wgs84_bbox"],
        "year":study["year"],
        "source_capture_at":study["retrieved_at"],
        "nifc_transport_claim":study["nifc_transport"],
        "mtbs_transport_claim":study["mtbs_transport"],
        "reviewers":reviewers,
        "candidates_checked":len(rows),
        "dispositions":{
            key:summary[key] for key in (
                "concordant_unverified_hypothesis","conflicting_hypotheses",
                "partially_inconclusive","both_inconclusive")},
        "cited_evidence_relation_counts":{
            key:citations[key] for key in (
                "same_cited_url_not_independent_sources",
                "different_cited_urls_not_source_independence",
                "one_or_both_sources_not_cited")},
        "candidates":rows,
        "same_fire_events_independently_verified":0,
        "independently_verified_nonfire_cases":0,
        "binary_prediction_labels_created":0,
        "model_skill_measured":False,
        "scientific_warnings":[
            "Two reviewers agreeing on a hypothesis is NOT verified same-event identity.",
            "Different reviewer identities cannot prove independent review or sources.",
            "Different citations can share upstream agency records; sources may be correlated.",
            "MTBS and NIFC may use common incident inputs; geographic overlap is a candidate only.",
            "MTBS mapped centroids are retrospective and prescribed burns may be present.",
            "Every disputed or inconclusive case stays unresolved, never cast as a binary fire/nonfire label.",
        ],
    }
    if len(_canonical(result))>MAX_OUTPUT_BYTES:
        raise ValueError("reconciliation report exceeds 1 MiB bounded research output")
    return result


def render_html(result:dict)->str:
    if (result.get("research_status")!="two_blind_reviewer_hypotheses_not_event_adjudication"
            or result.get("same_fire_events_independently_verified")!=0
            or result.get("independently_verified_nonfire_cases")!=0):
        raise ValueError("only explicitly unverified two-reviewer hypotheses may be rendered")
    e=lambda x:html.escape(str(x),quote=True)
    rows=[]
    for case in result["candidates"]:
        columns=[
            ("Candidate",case["candidate_id"]),
            ("MTBS",f"{case['mtbs']['source_fire_id']}: {case['mtbs']['name']} ({case['mtbs']['fire_type']})"),
            ("NIFC",f"ObjectID {case['nifc']['object_id']}: {case['nifc']['name']}"),
            ("Status",case["review_status"]),
        ]
        cells="".join('<td data-label="'+e(k)+'">'+e(v)+'</td>' for k,v in columns)
        for part in ("first","second"):
            reviewer=case[part]
            url=reviewer.get("evidence_url")
            source=('<a href="'+e(url)+'" rel="noreferrer noopener">'
                    "Cited source</a>" if url else "No source cited")
            label=f"{reviewer['reviewer_id']}: {reviewer['decision']}"
            cells+=('<td data-label="'+e(part.title())+'">'+e(label)+
                    "<details><summary>Review details</summary><p>"+e(reviewer["reason"])+
                    "</p><p>"+source+"</p></details></td>")
        cells+=('<td data-label="Evidence/review flags">'+
                e(case["cited_evidence_relation"])+"; "+
                e(", ".join(case["human_follow_up_flags"]) or "No extra flags")+"</td>")
        rows.append('<tr id="'+e(case["candidate_id"])+'">'+cells+"</tr>")
    labels=["Candidate","MTBS","NIFC","Status","First reviewer",
            "Second reviewer","Evidence/review flags"]
    headers="".join("<th scope='col'>"+e(t)+"</th>" for t in labels)
    metric="".join(
        "<div><strong>"+str(v)+"</strong><small>"+e(k.replace("_"," "))+"</small></div>"
        for k,v in result["dispositions"].items())
    css_digest=base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    csp="default-src 'none'; script-src 'none'; img-src 'none'; connect-src 'none'; object-src 'none'; base-uri 'none'; style-src 'sha256-"+css_digest+"'"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="'+e(csp)+'">'
        "<title>Research-only two-reviewer pair reconciliation</title>"
        "<style>"+STYLE+"</style></head><body>"
        "<header><h1>MTBS–NIFC independent review comparison</h1>"
        "<p>Original source SHA-256: <code>"+e(result["source_study_sha256"])+"</code></p>"
        "<p>Region: "+e(result["source_region_wgs84_bbox"])+
        " · Year: "+e(result["year"])+"</p>"
        '<p class="notice">All verdicts are human hypotheses; agreement does not validate '
        'same-fire identity, a reliable negative or scientific model accuracy. '
        'Reviewer identities and HTTPS citations are operator-declared and not externally authenticated. '
        'This private HTML is static and never uploads data.</p></header>'
        '<main><h2>Reviewer agreement and conflicts</h2><div class="summary">'+
        metric+"</div>"
        "<table><thead><tr>"+headers+"</tr></thead><tbody>"+
        "".join(rows)+"</tbody></table></main>"
        "<footer><p>Two source records may be close due to different incident definitions, "
        "mapping stages or shared agency inputs. Human research required before any "
        "event crosswalk or science claim.</p>"
        "<p>Verified event identities: 0 · Verified nonfire cases: 0 · "
        "Binary prediction labels: 0</p></footer></body></html>\n"
    )


def main()->None:
    parser=argparse.ArgumentParser(description="Reconcile separate MTBS–NIFC pair reviews without creating binary labels")
    parser.add_argument("--study-dir",required=True,type=Path)
    parser.add_argument("--first",required=True,type=Path)
    parser.add_argument("--second",required=True,type=Path)
    parser.add_argument("--json",required=True,type=Path)
    parser.add_argument("--html",required=True,type=Path)
    args=parser.parse_args()
    outputs=(args.json,args.html)
    inputs=(args.first,args.second,args.study_dir)
    if (args.json.resolve()==args.html.resolve() or
            any(p.exists() or p.resolve().is_relative_to(args.study_dir.resolve())
                or p.resolve() in {args.first.resolve(),args.second.resolve()}
                for p in outputs)):
        parser.error("both private review reports must be new, distinct and outside source archive")
    result=reconcile(args.study_dir,args.first,args.second)
    files=((args.json,json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n"),
           (args.html,render_html(result)))
    written=[]
    try:
        for path,content in files:
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open("x",encoding="utf-8") as stream:
                stream.write(content)
            written.append(path)
    except BaseException:
        for path in written:path.unlink()
        raise
    print(json.dumps({"source_candidates":result["candidates_checked"],
                      "unverified_agreed_hypotheses":result["dispositions"]["concordant_unverified_hypothesis"],
                      "disputed_or_unresolved":result["candidates_checked"]-
                                result["dispositions"]["concordant_unverified_hypothesis"],
                      "confirmed_event_identities":0,"negative_labels":0},sort_keys=True))


if __name__=="__main__":
    main()
