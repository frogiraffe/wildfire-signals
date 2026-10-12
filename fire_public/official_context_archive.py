"""Immutable official NIFC *context* archive, separated from binary outcome receipts.

Replays raw government GeoJSON against an immutable review queue and verifies
source digests. This never creates adjudicated fire/non-fire labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from .evidence_receipts import _archive_new
from .label_review import _load, _sha, _utc, MAX_REVIEW_BYTES
from .official_perimeters import SERVICE, RIGHTS_URL, _feature

MAX_BLOB = 8 * 1024 * 1024
MAX_MANIFEST = 512 * 1024


def canonical(value: dict) -> bytes:
    return (json.dumps(value,sort_keys=True,ensure_ascii=False,
                       separators=(",",":"),allow_nan=False)+"\n").encode()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def queue_leads(queue: Path) -> tuple[dict[str,dict],str]:
    q=_load(queue,MAX_REVIEW_BYTES)
    if q.get("schema_version")!=1 or q.get("state")!="unadjudicated_review_queue":
        raise ValueError("original source review queue required")
    cases=q.get("cases")
    if not isinstance(cases,list):
        raise ValueError("queue cases required")
    leads={}
    for case in cases:
        if not isinstance(case,dict):
            raise ValueError("malformed original queue case")
        if case.get("kind")!="retrospective_official_perimeter_review":
            continue
        cid=case.get("case_id")
        year=case.get("source_fire_year")
        oid=case.get("source_object_id")
        if (type(year) is not int or type(oid) is not int or
            cid!=f"official:{year}:{oid}" or case.get("source")!=SERVICE
                or cid in leads):
            raise ValueError("invalid official source case identity")
        leads[cid]=case
    if not 1<=len(leads)<=16:
        raise ValueError("official context archive supports 1..16 source leads")
    return leads,_sha(queue)


def validate_context(queue: Path, report: dict, raws: dict[str,bytes]) -> dict:
    leads,queue_sha=queue_leads(queue)
    if (report.get("status")!="official_source_reconciliation_completed"
            or report.get("original_queue_sha256")!=queue_sha
            or report.get("api_service")!=SERVICE
            or report.get("rights_url")!=RIGHTS_URL
            or report.get("transport") not in (
                "direct_pinned_official_https","injected_test_transport")):
        raise ValueError("source reconciliation report does not match official queue")
    if _utc(report["fresh_capture_at"])<_utc(_load(queue,MAX_REVIEW_BYTES)["as_of"]):
        raise ValueError("official source response capture predates queued evidence")
    findings=report.get("findings")
    files=report.get("source_response_evidence")
    if (not isinstance(findings,list) or len(findings)!=len(leads)
            or not isinstance(files,list) or
            not 1<=len(files)<=16 or len(files)!=len(raws)):
        raise ValueError("source response set does not cover original official leads")
    by_case={}
    for f in findings:
        cid=f.get("case_id") if isinstance(f,dict) else None
        if cid in by_case or cid not in leads:
            raise ValueError("extra or duplicate official context finding")
        if (f.get("source_year")!=leads[cid]["source_fire_year"]
                or f.get("object_id")!=leads[cid]["source_object_id"]
                or f.get("evidence_kind")!="retrospective_official_perimeter_positive_context"
                or f.get("independent_binary_outcome_verified") is not False
                or f.get("negative_label_created") is not False):
            raise ValueError("official context must not be promoted to an outcome label")
        by_case[cid]=f
    result_pages=[]
    covered=set()
    for item in files:
        if not isinstance(item,dict):
            raise ValueError("source page manifest invalid")
        name=item.get("filename")
        if not isinstance(name,str) or not name.startswith("nifc-year-") or not name.endswith("-response.geojson"):
            raise ValueError("invalid fixed-endpoint source filename")
        try:
            year=int(name.removeprefix("nifc-year-").removesuffix("-response.geojson"))
        except ValueError as error:
            raise ValueError("invalid source year in filename") from error
        if year in covered or name not in raws:
            raise ValueError("duplicate or absent source year response")
        raw=raws[name]
        if (type(raw) is not bytes or not 0<len(raw)<=MAX_BLOB or
                item.get("sha256")!=digest(raw) or item.get("bytes")!=len(raw)):
            raise ValueError("raw official source SHA-256 or byte count mismatch")
        page=json.loads(raw)
        selected={case["source_object_id"]:by_case[cid] for cid,case in leads.items()
                  if case["source_fire_year"]==year}
        if not selected or page.get("type")!="FeatureCollection" or not isinstance(page.get("features"),list):
            raise ValueError("official GeoJSON response missing for requested source year")
        if len(page["features"])!=len(selected):
            raise ValueError("incomplete official source page cannot indicate no fire")
        found=set()
        for raw_feature in page["features"]:
            parsed=_feature(raw_feature,year,set(selected))
            oid=parsed[1]
            if oid in found:
                raise ValueError("duplicate official object ID within raw response")
            found.add(oid)
            finding=selected[oid]
            if parsed[5]!=finding["fresh_feature_sha256"]:
                raise ValueError("official source polygon bytes contradict recorded feature hash")
            status=("same_content_as_archived" if
                    parsed[5]==finding["original_feature_sha256"] else
                    "source_revision_since_archival")
            if status!=finding.get("source_record_status"):
                raise ValueError("source revision status inconsistent with archived hashes")
            lead=leads[finding["case_id"]]
            expected=(str(lead["source_global_id"]).casefold() if
                      lead.get("source_global_id") else f"objectid:{oid}")
            if parsed[0]!=expected:
                raise ValueError("source GlobalID does not match original review queue")
        if found!=set(selected):
            raise ValueError("official source page did not include exact requested IDs")
        covered.add(year)
        result_pages.append({"filename":name,"year":year,
                             "sha256":digest(raw),"bytes":len(raw)})
    if covered!={v["source_fire_year"] for v in leads.values()}:
        raise ValueError("official source page years incomplete")
    if report.get("reviewed_official_leads")!=len(leads):
        raise ValueError("official review lead count disagrees with queue")
    return {
        "schema_version":1,
        "role":"retrospective_official_context_only",
        "source_url":SERVICE,"rights_url":RIGHTS_URL,
        "queue_sha256":queue_sha,
        "captured_at":report["fresh_capture_at"],
        "transport_claim":report["transport"],
        "transport_externally_authenticated_by_saved_bytes":False,
        "original_reconciliation":report,
        "response_pages":sorted(result_pages,key=lambda x:x["year"]),
        "official_case_ids":sorted(leads),
        "valid_binary_outcomes_created":0,
        "valid_negative_labels_created":0,
    }


def archive_context(queue: Path, report: dict, raws: dict[str,bytes],
                    store: Path) -> dict:
    entry=validate_context(queue,report,raws)
    if store.is_symlink() or not store.is_dir():
        raise ValueError("create private official context store directory first")
    base=store/"official-context"
    if base.is_symlink():
        raise ValueError("official context folder must not be symlink")
    serialized=canonical(entry)
    if len(serialized)>MAX_MANIFEST:
        raise ValueError("official context manifest too large")
    for descriptor in entry["response_pages"]:
        _archive_new(base/"blobs"/(descriptor["sha256"]+".geojson"),
                     raws[descriptor["filename"]])
    run_sha=digest(serialized)
    _archive_new(base/"runs"/(run_sha+".json"),serialized)
    return {"archive_run_sha256":run_sha,"queue_sha256":entry["queue_sha256"],
            "official_leads":len(entry["official_case_ids"]),
            "raw_pages":len(entry["response_pages"]),
            "transport_claim":entry["transport_claim"],
            "valid_binary_outcomes_created":0,
            "archive_prefix":"official-context/"}


def audit_context(queue: Path, store: Path, *, run_sha256: str | None = None) -> dict:
    leads,expected_queue_sha=queue_leads(queue)
    base=store/"official-context"
    runs=base/"runs"
    if (store.is_symlink() or base.is_symlink() or runs.is_symlink()
            or not runs.is_dir()):
        raise ValueError("private official-context run archive missing")
    files=sorted(runs.iterdir())
    if not 1<=len(files)<=100 or any(
            f.is_symlink() or not f.is_file() or f.suffix!=".json" or
            len(f.stem)!=64 or f.stat().st_size>MAX_MANIFEST for f in files):
        raise ValueError("missing, oversized or invalid official context manifest")
    if run_sha256 is not None:
        if len(run_sha256)!=64 or any(c not in "0123456789abcdef" for c in run_sha256):
            raise ValueError("run hash must be SHA-256 lower-case hex")
        selected=runs/(run_sha256+".json")
        if selected not in files:
            raise ValueError("requested official context run is missing")
    else:
        selected=max(files,key=lambda f:_utc(json.loads(f.read_text())["captured_at"]))
    blob=selected.read_bytes()
    if digest(blob)!=selected.stem:
        raise ValueError("official context manifest SHA-256 mismatch")
    entry=json.loads(blob)
    if entry.get("queue_sha256")!=expected_queue_sha:
        raise ValueError("official context belongs to another review queue")
    originals={}
    for descriptor in entry.get("response_pages",[]):
        name=descriptor["filename"]
        sha=descriptor["sha256"]
        if len(sha)!=64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("invalid source hash")
        src=base/"blobs"/(sha+".geojson")
        if src.is_symlink() or not src.is_file() or src.stat().st_size>MAX_BLOB:
            raise ValueError("raw official source blob missing or too large")
        raw=src.read_bytes()
        if digest(raw)!=sha or len(raw)!=descriptor["bytes"]:
            raise ValueError("official source blob SHA-256 mismatch")
        originals[name]=raw
    checked=validate_context(queue,entry["original_reconciliation"],originals)
    if canonical(checked)!=blob:
        raise ValueError("archive metadata does not match original official response bytes")
    return {
        "schema_version":1,"archive_run_sha256":selected.stem,
        "queue_sha256":expected_queue_sha,
        "captured_at":entry["captured_at"],
        "transport_claim":entry["transport_claim"],
        "transport_externally_authenticated_by_saved_bytes":False,
        "official_source_context_consistent":True,
        "official_leads":len(leads),
        "verified_raw_source_pages":len(originals),
        "case_findings":[{
            "case_id":f["case_id"],"source_record_status":f["source_record_status"],
            "fresh_feature_sha256":f["fresh_feature_sha256"],
            "context_captured_at":entry["captured_at"],
            "independent_outcome_verified":False,
        } for f in entry["original_reconciliation"]["findings"]],
        "valid_binary_outcomes_created":0,
        "valid_negative_labels_created":0,
        "scientific_limit":"Verified source bytes are retrospective context, not wildfire/nonfire adjudication.",
    }


def main() -> None:
    parser=argparse.ArgumentParser(description="Audit non-label government source context by original research queue")
    parser.add_argument("--queue",required=True,type=Path)
    parser.add_argument("--store",required=True,type=Path)
    parser.add_argument("--run-sha256")
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    if (args.output.exists() or args.output.resolve().is_relative_to(args.store.resolve())
            or args.output.resolve()==args.queue.resolve()):
        parser.error("output must be new and outside source/context archives")
    result=audit_context(args.queue,args.store,run_sha256=args.run_sha256)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as handle:
        json.dump(result,handle,indent=2,sort_keys=True,ensure_ascii=False)
        handle.write("\n")
    print(json.dumps({"context_leads":result["official_leads"],
                      "raw_pages_checked":result["verified_raw_source_pages"],
                      "binary_outcomes_created":0},sort_keys=True))


if __name__=="__main__":
    main()
