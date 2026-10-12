"""Optional fail-closed geographic + temporal admission audit for negative cases.

Matches a declared independently enumerated frame *rectangle* to a separately
documented registry's rectangle and continuous data-observation windows. Requires
existing captured source snapshots and their reviewer bindings. It verifies
contracts, not government registry completeness or true fire absence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import timedelta
from pathlib import Path

from .label_review import (_load, _sha, _text, _utc, _url,
                           MAX_FRAME_BYTES, MAX_REVIEW_BYTES)
from .labeled_evaluation import _manifest
from .evidence_receipts import audit_receipts, _store_receipts

MAX_REGISTRY_AREAS=200
MAX_WINDOWS=2000


def bbox(value: object, name: str) -> tuple[float,float,float,float]:
    """Conservative WGS84 rectangle; antimeridian-crossing needs explicit split."""
    if (not isinstance(value,list) or len(value)!=4 or
            any(type(x) not in (int,float) for x in value)):
        raise ValueError(f"{name} requires [west,south,east,north] WGS84 rectangle")
    import math
    west,south,east,north=value
    if (not all(math.isfinite(x) for x in value) or not -180<=west<east<=180
            or not -90<=south<north<=90):
        raise ValueError(f"{name} must be ordered non-wrapping WGS84 rectangle")
    return tuple(float(x) for x in value)


def contains(outer: tuple, inner: tuple) -> bool:
    return (outer[0]<=inner[0] and outer[1]<=inner[1] and
            outer[2]>=inner[2] and outer[3]>=inner[3])


def overlaps(x: tuple, y: tuple) -> bool:
    return x[0]<y[1] and y[0]<x[1]


def admit_coverage(queue_path: Path, reviews_path: Path, protocol_path: Path,
                   registry_path: Path, evidence_store: Path) -> dict:
    """Validate real source *claim* provenance and deny all uncertain windows."""
    q=_load(queue_path,MAX_REVIEW_BYTES)
    reviews=_load(reviews_path,MAX_REVIEW_BYTES)
    protocol=_load(protocol_path,MAX_FRAME_BYTES)
    registry=_load(registry_path,MAX_FRAME_BYTES)
    if registry.get("schema_version")!=1:
        raise ValueError("coverage registry schema_version 1 required")
    if (reviews.get("queue_sha256")!=_sha(queue_path) or
            q.get("state")!="unadjudicated_review_queue"):
        raise ValueError("review decisions do not match source queue")
    _manifest(protocol)
    horizon=float(protocol["horizon_hours"])
    source_audit=audit_receipts(queue_path,reviews_path,evidence_store)
    if not source_audit["structurally_receipt_complete"]:
        raise ValueError("source receipt archive must bind every adjudicated review")
    source_receipts,_=_store_receipts(evidence_store)
    all_cases=q.get("cases")
    all_decisions=reviews.get("decisions")
    if not isinstance(all_cases,list) or not isinstance(all_decisions,list):
        raise ValueError("case and decision collections required")
    by_case={row["case_id"]:row for row in all_cases}
    by_review={row["case_id"]:row for row in all_decisions}
    if (len(by_case)!=len(all_cases) or len(by_review)!=len(all_decisions)
            or set(by_case)!=set(by_review)):
        raise ValueError("every unique source case must have a review decision")
    areas=registry.get("areas")
    if not isinstance(areas,list) or not 1<=len(areas)<=MAX_REGISTRY_AREAS:
        raise ValueError("coverage registry needs 1..200 area declarations")
    indexed={}
    for area in areas:
        if not isinstance(area,dict):
            raise ValueError("coverage declaration must be a structured area")
        region=_text(area.get("region_id"),"registry region")
        provider=_text(area.get("provider_id"),"registry provider",4)
        key=(region,provider)
        if key in indexed:
            raise ValueError("duplicate provider coverage declaration for region")
        if not _url(area.get("source_url")) or not _url(area.get("rights_url")):
            raise ValueError("independent registry source and licensing URLs required")
        coverage_box=bbox(area.get("coverage_bbox"),"registry spatial coverage")
        _text(area.get("inclusion_protocol"),"outcome observation inclusion protocol",8)
        intervals=area.get("windows")
        if not isinstance(intervals,list) or not 1<=len(intervals)<=MAX_WINDOWS:
            raise ValueError("coverage source needs 1..2000 declared windows")
        windows=[]
        for w in intervals:
            if not isinstance(w,dict) or w.get("status") not in (
                    "declared_complete","reported_gap","unknown"):
                raise ValueError("source observation status must be explicit")
            start=_utc(w.get("start_at"))
            end=_utc(w.get("end_at"))
            if end<=start:
                raise ValueError("coverage observation window has invalid interval")
            windows.append((start,end,w["status"]))
        indexed[key]={**area,"_bbox":coverage_box,"_windows":windows}
    results=[]
    checks=0
    denied=0
    for case_id,case in by_case.items():
        decision=by_review[case_id]
        if decision.get("status")!="adjudicated" or decision.get("label")!=0:
            continue
        checks+=1
        reasons=[]
        if case.get("kind")!="independent_frame_review":
            reasons.append("negative_not_from_independent_frame")
        declared=case.get("study_bbox")
        try:
            frame_bbox=bbox(declared,"frame complete study footprint")
        except ValueError:
            frame_bbox=None
            reasons.append("frame_footprint_missing_or_invalid")
        if frame_bbox is not None and not (
                frame_bbox[0]<=case.get("longitude",-999)<=frame_bbox[2] and
                frame_bbox[1]<=case.get("latitude",-999)<=frame_bbox[3]):
            reasons.append("frame_anchor_outside_study_footprint")
        if decision.get("region_id")!=case.get("region_id") or (
                decision.get("decision_at")!=case.get("decision_at")):
            reasons.append("review_region_or_time_differs_from_frame")
        start=_utc(decision["decision_at"])
        end=start+timedelta(hours=horizon)
        coverage=decision.get("negative_coverage") or {}
        expected_url=coverage.get("completeness_evidence_url")
        bindings=[x for x in source_audit["review_bindings"]
                  if x["case_id"]==case_id and x["role"]=="coverage"]
        matching_receipts=[source_receipts[b["receipt_id"]] for b in bindings]
        region_candidates=[
            item for (region,_provider),item in indexed.items()
            if region==case.get("region_id") and item["source_url"]==expected_url]
        if len(region_candidates)!=1:
            reasons.append("missing_or_ambiguous_independent_registry_scope")
        else:
            provider=region_candidates[0]
            if frame_bbox is not None and not contains(provider["_bbox"],frame_bbox):
                reasons.append("frame_footprint_outside_provider_spatial_scope")
            if (len(matching_receipts)!=1 or
                    matching_receipts[0]["source_url"]!=provider["source_url"] or
                    matching_receipts[0]["source_record_id"]!=provider.get("source_record_id") or
                    matching_receipts[0].get("coverage_region_id")!=case.get("region_id")):
                reasons.append("provider_scope_not_bound_to_archived_coverage_receipt")
            if not reasons:
                unknown=[(a,b) for a,b,status in provider["_windows"]
                         if status!="declared_complete" and overlaps((a,b),(start,end))]
                if unknown:
                    reasons.append("outage_or_unknown_interval_intersects_prediction_window")
                else:
                    complete=sorted((a,b) for a,b,status in provider["_windows"]
                                    if status=="declared_complete" and overlaps((a,b),(start,end)))
                    cursor=start
                    for a,b in complete:
                        if a>cursor:
                            break
                        if b>cursor:
                            cursor=b
                        if cursor>=end:
                            break
                    if cursor<end:
                        reasons.append("continuous_observation_window_not_established")
        denied+=bool(reasons)
        results.append({
            "case_id":case_id,"region_id":case.get("region_id"),
            "decision_at":decision["decision_at"],
            "prediction_end_at":end.isoformat(),
            "admission":("declared_scope_structurally_complete" if not reasons
                         else "not_admitted"),
            "reasons":reasons,
            "observation_scope_independently_authenticated":False,
            "fire_absence_independently_verified":False,
        })
    if not checks:
        raise ValueError("there are no adjudicated negative cases to inspect")
    return {
        "schema_version":1,
        "queue_sha256":_sha(queue_path),
        "reviews_sha256":_sha(reviews_path),
        "protocol_sha256":_sha(protocol_path),
        "registry_sha256":_sha(registry_path),
        "archived_source_receipts_sha256":source_audit["source_receipts_sha256"],
        "negative_cases_checked":checks,
        "admitted_declarations":checks-denied,
        "denied":denied,
        "structurally_complete":denied==0,
        "cases":sorted(results,key=lambda x:x["case_id"]),
        "registry_claims_operator_supplied":True,
        "independent_nonfire_truth_verified":False,
        "scientific_limit":(
            "Geographic rectangles and observed intervals are declared by an operator. "
            "Passing validates internal scope and preserved source bytes only, NOT registry "
            "completeness, independent non-fire outcomes or calibrated predictions."),
    }


def main() -> None:
    parser=argparse.ArgumentParser(description="Offline strict negative-case observation-scope audit")
    parser.add_argument("--queue",required=True,type=Path)
    parser.add_argument("--reviews",required=True,type=Path)
    parser.add_argument("--protocol",required=True,type=Path)
    parser.add_argument("--registry",required=True,type=Path)
    parser.add_argument("--evidence-store",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    inputs=(args.queue,args.reviews,args.protocol,args.registry)
    if args.output.exists() or any(args.output.resolve()==x.resolve() for x in inputs):
        parser.error("new audit output required; do not overwrite research evidence")
    result=admit_coverage(args.queue,args.reviews,args.protocol,
                          args.registry,args.evidence_store)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as output:
        json.dump(result,output,ensure_ascii=False,sort_keys=True,indent=2)
        output.write("\n")
    print(json.dumps({"checked":result["negative_cases_checked"],
                      "denied":result["denied"],
                      "structurally_complete":result["structurally_complete"],
                      "independent_nonfire_truth_verified":False},sort_keys=True))


if __name__=="__main__":
    main()
