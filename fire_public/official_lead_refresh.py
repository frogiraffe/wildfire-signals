"""Reconcile actual archived NIFC review leads with *new* live source bytes.

The fixed, read-only NIFC API is queried only for official positive-context
perimeter leads in an existing audited review queue. HTTP responses are
preserved verbatim and tied to the original queue and source archive by SHA.
This never authenticates binary wildfire outcomes or absence of fires.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .history import _timestamp
from .label_review import _load, _sha, MAX_REVIEW_BYTES
from .official_live_probe import _get_layer_metadata, validate_layer_metadata
from .official_perimeters import (
    QUERY_URL, RIGHTS_URL, SERVICE, MAX_RESPONSE_BYTES, _RejectRedirects,
    _feature, _canonical,
)
from .perimeter_study import study_report

MAX_LEADS = 16
MAX_RAW_FILE = 8 * 1024 * 1024


def _fetch_direct(params: dict) -> bytes:
    """Exactly the known NIFC HTTPS endpoint; no user-controlled URL or redirects."""
    request = Request(QUERY_URL + "?" + urlencode(params),
                      headers={"Accept": "application/geo+json, application/json",
                               "User-Agent": "WildfireSignals-OfficialLeadVerification/1"})
    with build_opener(_RejectRedirects()).open(request, timeout=45) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if not raw or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("empty or oversized official NIFC GeoJSON response")
    return raw


def verify_leads(queue: Path, archive: Path, *,
                 max_leads: int = 8, fetch_page=None,
                 fetch_metadata=None, clock=None) -> tuple[dict, dict[str, bytes]]:
    """Check queue identities and source revisions; preserve genuine response bytes.

    Public TLS origin is checked by the standard HTTP library on *direct* calls.
    Test transport injection is marked explicitly; no synthetic data can be
    labeled direct-HTTPS evidence from this entrypoint.
    """
    if type(max_leads) is not int or not 1 <= max_leads <= MAX_LEADS:
        raise ValueError("max_leads must be an integer from 1 to 16")
    q = _load(queue, MAX_REVIEW_BYTES)
    if q.get("schema_version") != 1 or q.get("state") != "unadjudicated_review_queue":
        raise ValueError("only a genuine prepared unadjudicated research queue is supported")
    cases = q.get("cases")
    batches = q.get("source_batches")
    if not isinstance(cases, list) or not isinstance(batches, list) or not batches:
        raise ValueError("original source queue and source batch provenance required")
    original = [item for item in cases if isinstance(item, dict) and
                item.get("kind") == "retrospective_official_perimeter_review"]
    if not original:
        raise ValueError("there are no official perimeter source leads to verify")
    if len(original) > max_leads:
        raise ValueError("number of official source leads exceeds explicit review budget")
    all_ids = [c.get("case_id") for c in cases]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("review queue contains duplicate identities")
    requested = defaultdict(list)
    for lead in original:
        year = lead.get("source_fire_year")
        oid = lead.get("source_object_id")
        if (type(year) is not int or type(oid) is not int or oid < 0 or
                lead.get("case_id") != f"official:{year}:{oid}" or
                lead.get("source") != SERVICE):
            raise ValueError("malformed or non-NIFC government source lead")
        requested[year].append(lead)
    source_batches = {}
    for batch in batches:
        if not isinstance(batch, dict):
            raise ValueError("invalid archived source batch")
        year = batch.get("fire_year")
        digest = batch.get("batch_id")
        if type(year) is not int or not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("invalid source batch identity")
        if year in source_batches:
            raise ValueError("multiple source batches for one fire year")
        source_batches[year] = digest
    if set(requested) != set(source_batches):
        raise ValueError("source lead years and archived batch years are inconsistent")
    archived, geo = study_report(
        archive, at=q["as_of"], years=sorted(requested),
        required_batches=source_batches)
    if not archived["complete_requested_year_sample"]:
        raise ValueError("original official source batch is not retrievable at queue cutoff")
    feature_map = {}
    for original_feature in geo["features"]:
        props = original_feature["properties"]
        key = (props["FIRE_YEAR_INT"], props["OBJECTID"])
        if key in feature_map:
            raise ValueError("duplicate official source geometry in archived batch")
        feature_map[key] = original_feature
    if set(feature_map) != {
            (c["source_fire_year"], c["source_object_id"]) for c in original}:
        raise ValueError("review queue differs from recorded government source sample")
    for c in original:
        p = feature_map[(c["source_fire_year"], c["source_object_id"])]["properties"]
        if (c.get("source_global_id") != p.get("GlobalID") or
                c.get("source_name") != p.get("INCIDENT")):
            raise ValueError("review queue official source identity or name was altered")
    metadata = validate_layer_metadata(
        _get_layer_metadata() if fetch_metadata is None else fetch_metadata())
    verified_at = _timestamp(clock() if clock is not None
                             else datetime.now(timezone.utc).isoformat())
    if verified_at < _timestamp(q["as_of"]):
        raise ValueError("live verification cannot predate original queue archive")
    getter = _fetch_direct if fetch_page is None else fetch_page
    files = {}
    findings = []
    for year in sorted(requested):
        selected = sorted(requested[year],key=lambda v:v["source_object_id"])
        ids = [c["source_object_id"] for c in selected]
        params = {"f":"geojson", "objectIds":",".join(map(str,ids)),
                  "outFields":"*", "outSR":"4326",
                  "returnGeometry":"true", "orderByFields":"OBJECTID"}
        raw = getter(params)
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_RAW_FILE:
            raise ValueError("raw NIFC response must be bounded exact HTTP bytes")
        reply = json.loads(raw)
        if (not isinstance(reply,dict) or reply.get("type") != "FeatureCollection" or
                not isinstance(reply.get("features"),list) or
                len(reply["features"]) != len(ids)):
            raise ValueError("official source missing requested polygon(s), not evidence of fire absence")
        rows = [_feature(v,year,set(ids)) for v in reply["features"]]
        if len({r[1] for r in rows}) != len(ids) or {r[1] for r in rows} != set(ids):
            raise ValueError("official polygon response returned wrong or repeated source IDs")
        by_oid = {r[1]: r for r in rows}
        for c in selected:
            oid = c["source_object_id"]
            stored = feature_map[(year,oid)]
            official = by_oid[oid]
            actual_identity = official[0]
            expected = (str(c["source_global_id"]).casefold()
                        if c.get("source_global_id") else f"objectid:{oid}")
            if actual_identity != expected:
                raise ValueError("official polygon source GlobalID changed; manual investigation required")
            old = _feature({"type":"Feature","properties":stored["properties"],
                            "geometry":stored["geometry"]},year,{oid})
            findings.append({
                "case_id":c["case_id"], "source_year":year, "object_id":oid,
                "original_feature_sha256":old[5],
                "fresh_feature_sha256":official[5],
                "source_record_status":("same_content_as_archived" if old[5] == official[5]
                                        else "source_revision_since_archival"),
                "evidence_kind":"retrospective_official_perimeter_positive_context",
                "independent_binary_outcome_verified":False,
                "negative_label_created":False,
            })
        files[f"nifc-year-{year}-response.geojson"] = raw
    report = {
        "schema_version":1,
        "status":"official_source_reconciliation_completed",
        "original_queue_sha256":_sha(queue),
        "original_archive_as_of":archived["decision_at"],
        "archive_source_batches": source_batches,
        "fresh_capture_at":verified_at,
        "api_service":SERVICE,
        "rights_url":RIGHTS_URL,
        "source_layer_metadata_sha256":metadata["schema_sha256"],
        "transport":("direct_pinned_official_https"
                     if fetch_page is None and fetch_metadata is None
                     else "injected_test_transport"),
        "official_source_requests":len(files),
        "reviewed_official_leads":len(findings),
        "source_revisions":sum(f["source_record_status"] ==
                                "source_revision_since_archival" for f in findings),
        "source_response_evidence":[{"filename":name,
              "sha256":hashlib.sha256(raw).hexdigest(),
              "bytes":len(raw)} for name,raw in sorted(files.items())],
        "findings":findings,
        "independent_outcomes_verified":0,
        "independently_verified_negative_labels":0,
        "model_ready":False,
        "notes":[
            "Fixed-endpoint HTTPS transport proves a current NIFC service response, not a publisher-signed historic record.",
            "Retrospective perimeter records are positive-context leads, not independent incident occurrence outcomes.",
            "Source revisions represent provider changes since archival, not actual fire growth.",
            "A missing official polygon fails this verification; it never means a fire was absent.",
            "In injected tests no genuine TLS/source origin has been authenticated.",
        ],
    }
    return report, files


def write_evidence(output: Path, source_dir: Path,
                   report: dict, blobs: dict[str, bytes],
                   *, input_files: tuple[Path, ...]) -> None:
    if (output.exists() or source_dir.exists() or
            output.resolve().is_relative_to(source_dir.resolve()) or
            any(p.resolve() in {output.resolve(),source_dir.resolve()}
                for p in input_files)):
        raise ValueError("source archive and evidence outputs must be new and disjoint")
    source_dir.parent.mkdir(parents=True,exist_ok=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    source_dir.mkdir(mode=0o700)
    try:
        for name,raw in sorted(blobs.items()):
            if not name.startswith("nifc-year-") or not name.endswith("-response.geojson"):
                raise ValueError("unsafe source response output name")
            with (source_dir/name).open("xb") as fd:
                fd.write(raw)
        with output.open("x",encoding="utf-8") as fd:
            json.dump(report,fd,sort_keys=True,ensure_ascii=False,indent=2)
            fd.write("\n")
    except BaseException:
        # These paths are new; remove only artifacts created during this call.
        for path in source_dir.iterdir():
            if path.is_file():
                path.unlink()
        source_dir.rmdir()
        if output.is_file():
            output.unlink()
        raise


def main() -> None:
    parser=argparse.ArgumentParser(description="Bounded live official source refresh of archived NIFC review leads")
    parser.add_argument("--queue",type=Path,required=True)
    parser.add_argument("--perimeter-db",type=Path,required=True)
    parser.add_argument("--max-leads",type=int,default=8)
    parser.add_argument("--json",type=Path,required=True)
    parser.add_argument("--source-dir",type=Path,required=True)
    args=parser.parse_args()
    report,blobs=verify_leads(args.queue,args.perimeter_db,max_leads=args.max_leads)
    write_evidence(args.json,args.source_dir,report,blobs,
                   input_files=(args.queue,args.perimeter_db))
    print(json.dumps({"official_leads":report["reviewed_official_leads"],
                      "source_revisions":report["source_revisions"],
                      "transport":report["transport"],
                      "report":str(args.json)},sort_keys=True))


if __name__=="__main__":
    main()
