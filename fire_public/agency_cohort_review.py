"""Private, read-only bridge between unlabeled FIRMS study frames and agency receipts.

A prospective agency listing within a region is a *review lead*, not a
new-ignition label, independently identified fire, or source-complete negative.
No training features are updated with future agency observations.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import closing
from datetime import timedelta
import hashlib
from html import escape
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from urllib.parse import quote

from .history import _timestamp
from .observational_cohort import _canonical, REGION_ID
from .receipt_history import SOURCES
from .region_diagnostics import distance_km

ROOT = Path(__file__).resolve().parents[1]
MAX_SAMPLES = 256
MAX_AGENCY_SCANS = 400
MAX_LEADS = 2000
MAX_COHORT_BYTES = 10 * 1024 * 1024
MAX_AGENCY_ROWS = 250000
MAX_HTML_BYTES = 2 * 1024 * 1024


def _ro(path: Path) -> sqlite3.Connection:
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.resolve().is_relative_to(ROOT):
        raise ValueError("existing private original agency database required")
    conn = sqlite3.connect("file:"+quote(str(path.resolve()),safe="/")+"?mode=ro",uri=True)
    conn.row_factory=sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"receipt_scans","receipt_sources","receipt_presence","observations"}.issubset(tables):
            raise ValueError("agency source receipts not imported")
    except Exception:
        conn.close()
        raise
    return conn


def read_unlabeled_cohort(folder: Path) -> tuple[dict,list[dict],str]:
    """Verify original v3 manifest and full JSONL bytes before any join."""
    folder=Path(folder)
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("existing private v3 cohort required")
    manifest_path=folder/"manifest.json"
    records_path=folder/"observations.jsonl"
    for item in (manifest_path,records_path):
        if item.is_symlink() or not item.is_file() or item.stat().st_size>MAX_COHORT_BYTES:
            raise ValueError("missing or oversized cohort manifest/records")
    raw=records_path.read_bytes()
    manifest=json.loads(manifest_path.read_bytes())
    if (not isinstance(manifest,dict) or
        manifest.get("kind")!="unlabeled_prospective_satellite_observation_study_frame" or
        manifest.get("schema_version")!=1 or
        manifest.get("sampling_frame_locked_before_labels") is not True or
        manifest.get("no_negative_label_inferred_from_missing_detection") is not True or
        manifest.get("no_satellite_acquisition_denominator") is not True):
        raise ValueError("unrecognized or improperly labeled source study frame")
    stored=manifest.get("files",{}).get("observations.jsonl",{})
    if stored.get("sha256")!=hashlib.sha256(raw).hexdigest():
        raise ValueError("cohort source record SHA-256 mismatch")
    rows=[json.loads(line) for line in raw.splitlines() if line]
    if (not 1<=len(rows)<=MAX_SAMPLES or
        stored.get("rows")!=len(rows) or
        manifest.get("counts",{}).get("rows")!=len(rows)):
        raise ValueError("cohort row count mismatch")
    seen=set()
    for row in rows:
        if (not isinstance(row,dict) or
            row.get("sample_id") in seen or
            not isinstance(row.get("sample_id"),str) or
            not re.fullmatch(r"signal-study-[a-f0-9]{24}",row["sample_id"]) or
            not REGION_ID.fullmatch(str(row.get("region_id",""))) or
            row.get("unit")!="preselected_geodesic_region_at_decision_time_not_fire_event" or
            row.get("target_label") is not None or
            row.get("model_training_allowed") is not False or
            row.get("independent_label_source") is not None or
            row.get("split_assignment")!="unassigned"):
            raise ValueError("review bridge accepts only distinct completely UNLABELED V3 rows")
        seen.add(row["sample_id"])
        start, decision, end=(_timestamp(row[key]) for key in
            ("feature_window_start_at","decision_at","outcome_window_end_exclusive"))
        if (row.get("feature_window_end_exclusive")!=row["decision_at"] or
            row.get("outcome_window_start_at")!=row["decision_at"] or
            not start<decision<end or row.get("source_first_captured_no_later_than")!=decision):
            raise ValueError("source cohort decision/capture time contract broken")
        if row["region_id"] not in {r["region_id"] for r in manifest["sampling_regions"]}:
            raise ValueError("cohort region is outside preregistered geography")
        item=next(r for r in manifest["sampling_regions"] if r["region_id"]==row["region_id"])
        if any(row.get(key)!=item[key] for key in ("latitude","longitude","radius_km")):
            raise ValueError("cohort location differs from locked sampling frame")
    return manifest, rows, hashlib.sha256(manifest_path.read_bytes()).hexdigest()


def build_agency_review_candidates(folder: Path, agency_db: Path, *,
                                   through: str | None = None) -> dict:
    """Bounded source-evidence review leads with explicit provider coverage flags.

    A captured/listed point near the sampled circle is only a *possible
    association*. A previously known official ID is not a new fire; a newly
    listed ID is not independent evidence of ignition during the horizon.
    """
    manifest,samples,manifest_sha=read_unlabeled_cohort(folder)
    limit=_timestamp(through) if through else None
    last_future=max(_timestamp(s["outcome_window_end_exclusive"]) for s in samples)
    first_decision=min(_timestamp(s["decision_at"]) for s in samples)
    all_cases=[]
    counts=Counter()
    for row in samples:
        counts["sampled_region_decisions"]+=1
    with closing(_ro(agency_db)) as db:
        scan_rows=db.execute("""
            SELECT s.scan_at,s.captured_at,s.receipt_sha256,s.run_id,r.provider,r.status
            FROM receipt_scans s JOIN receipt_sources r ON r.scan_at=s.scan_at
            WHERE s.captured_at <= ? AND s.scan_at <= ?
            ORDER BY s.captured_at,s.scan_at,r.provider LIMIT ?
        """, (min(last_future,limit) if limit else last_future,
              min(last_future,limit) if limit else last_future,
              MAX_AGENCY_SCANS*len(SOURCES)+1)).fetchall()
        distinct={r["scan_at"] for r in scan_rows}
        if len(distinct)>MAX_AGENCY_SCANS or len(scan_rows)>MAX_AGENCY_SCANS*len(SOURCES):
            raise ValueError("agency study exceeds bounded original scan population")
        if len(scan_rows)!=len(distinct)*len(SOURCES):
            raise ValueError("source scan rows incomplete")
        by_scan=Counter()
        for scan in scan_rows:
            if (scan["status"] not in {"complete","failed","deferred"} or
                not re.fullmatch(r"[a-f0-9]{64}",str(scan["receipt_sha256"])) or
                not re.fullmatch(r"[1-9]\d*",str(scan["run_id"])) or
                _timestamp(scan["scan_at"])>_timestamp(scan["captured_at"])):
                raise ValueError("agency original scan metadata invalid")
            by_scan[(scan["scan_at"],scan["provider"])]+=1
        if any(n!=1 for n in by_scan.values()):
            raise ValueError("duplicate source scan states")
        # Only first listed identities of original source scans. Read the
        # captured, original incident payload for point/date provenance.
        presence=db.execute("""
            SELECT p.scan_at,p.provider,p.official_id,p.agency_status,
                   s.captured_at,s.receipt_sha256,s.run_id
            FROM receipt_presence p JOIN receipt_scans s ON s.scan_at=p.scan_at
            JOIN receipt_sources state ON state.scan_at=s.scan_at
                                     AND state.provider=p.provider
            WHERE s.captured_at <= ? AND s.scan_at <= ? AND state.status='complete'
            ORDER BY s.captured_at,s.scan_at,p.provider,p.official_id LIMIT ?
        """, (min(last_future,limit) if limit else last_future,
              min(last_future,limit) if limit else last_future,
              MAX_AGENCY_ROWS+1)).fetchall()
        if len(presence)>MAX_AGENCY_ROWS:
            raise ValueError("agency receipt incident population exceeds safe review limit")
        identities=Counter()
        for p in presence:
            identities[(p["provider"],p["official_id"])]+=1
        # Bulk load only observations attached to those original source
        # identities; observation time can predate receipt, so never join by
        # modified_at for availability, only original captured_at.
        observations=db.execute("""
            SELECT provider,source_id,captured_at,id,payload_json,rights_url
            FROM observations
            WHERE subject_kind='agency_incident' AND record_type='incident_status'
              AND captured_at <= ?
            ORDER BY provider,source_id,captured_at,id LIMIT ?
        """, (min(last_future,limit) if limit else last_future,
              MAX_AGENCY_ROWS+1)).fetchall()
        if len(observations)>MAX_AGENCY_ROWS:
            raise ValueError("agency observed provenance exceeds bounded review limit")
    by_identity={}
    for obs in observations:
        payload=json.loads(obs["payload_json"])
        if (not isinstance(payload,dict) or
            payload.get("provider")!=obs["provider"] or
            payload.get("official_id")!=obs["source_id"] or
            not re.fullmatch(r"[a-f0-9]{64}",str(obs["id"])) or
            not str(obs["rights_url"]).startswith("https://")):
            raise ValueError("corrupt original agency identity/provenance")
        by_identity.setdefault((obs["provider"],obs["source_id"]),[]).append((obs,payload))
    ordered={}
    for p in presence:
        key=(p["provider"],p["official_id"])
        evidence=[item for item in by_identity.get(key,[]) if
                  _timestamp(item[0]["captured_at"])<=_timestamp(p["captured_at"])]
        if not evidence:
            raise ValueError("listed source identity missing its verified original observation")
        latest=max(_timestamp(x[0]["captured_at"]) for x in evidence)
        match=[x for x in evidence if _timestamp(x[0]["captured_at"])==latest]
        if len(match)!=1:
            raise ValueError("same capture time has conflicting source identity payloads")
        original,payload=match[0]
        if payload.get("agency_status")!=p["agency_status"]:
            raise ValueError("archived agency status does not match original scan")
        for axis,lo,hi in (("latitude",-90,90),("longitude",-180,180)):
            x=payload.get(axis)
            if type(x) not in (int,float) or not lo<=x<=hi:
                raise ValueError("invalid original agency point")
        ordered.setdefault(key,[]).append({
            "provider":p["provider"],"official_id":p["official_id"],
            "agency_status":p["agency_status"],
            "point":[payload["latitude"],payload["longitude"]],
            "source_name":payload.get("name"),
            "captured_at":p["captured_at"],"scan_at":p["scan_at"],
            "receipt_sha256":p["receipt_sha256"],"observation_sha256":original["id"],
            "rights_url":original["rights_url"],"run_id":p["run_id"],
            "source_modified_at":payload.get("modified_at")
        })
    for key in ordered:
        ordered[key].sort(key=lambda a:(a["captured_at"],a["scan_at"]))
    for sample in samples:
        start=_timestamp(sample["decision_at"])
        stop=_timestamp(sample["outcome_window_end_exclusive"])
        effective_stop=min(stop,limit) if limit else stop
        provider_health={}
        for provider in SOURCES:
            prior=[x for x in scan_rows if x["provider"]==provider and x["captured_at"]<=start]
            future=[x for x in scan_rows if x["provider"]==provider and
                    start<x["captured_at"]<effective_stop]
            last_pre=prior[-1] if prior else None
            provider_health[provider]={
                "pre_decision_source_status":last_pre["status"] if last_pre else None,
                "pre_decision_receipt_at":last_pre["captured_at"] if last_pre else None,
                "post_decision_source_receipts":len(future),
                "post_decision_complete_receipts":sum(x["status"]=="complete" for x in future),
                "post_decision_failed_receipts":sum(x["status"]=="failed" for x in future),
                "post_decision_deferred_receipts":sum(x["status"]=="deferred" for x in future),
                "horizon_fully_audited":False, # no independent complete event census
            }
        lead_rows=[]
        for (provider,oid),records in sorted(ordered.items()):
            in_circle=[x for x in records if
                distance_km(sample["latitude"],sample["longitude"],
                            *x["point"])<=sample["radius_km"]]
            if not in_circle:continue
            before=[x for x in in_circle if x["captured_at"]<=start]
            future=[x for x in in_circle if start<x["captured_at"]<effective_stop]
            if not future:continue
            first=future[0]
            latest=future[-1]
            confidence="preexisting_agency_source_listing" if before else (
                "first_in_available_receipt_history_not_proven_ignition")
            lead_rows.append({
                "review_lead_id":"agency-candidate-"+hashlib.sha256(_canonical([
                    sample["sample_id"],provider,oid
                ])).hexdigest()[:24],
                "sample_id":sample["sample_id"],
                "agency_provider":provider,"official_id":oid,
                "agency_name_at_last_listed_receipt":latest["source_name"],
                "first_post_decision_listed_at":first["captured_at"],
                "prior_listed_in_available_history":bool(before),
                "lead_status":confidence,
                "latest_captured_status":latest["agency_status"],
                "agency_incident_point_wgs84":latest["point"],
                "last_source_scan_at":latest["scan_at"],
                "run_id":latest["run_id"],
                "receipt_sha256":latest["receipt_sha256"],
                "original_observation_sha256":latest["observation_sha256"],
                "source_modified_at":latest["source_modified_at"],
                "source_rights_url":latest["rights_url"],
                "event_identity_verified":False,
                "independent_outcome_label":None,
                "negative_fire_label":None,
                "ignition_time_established":False,
                "satellite_association_verified":False,
                "review_status":"unresolved",
                "interpretation":"Agency point near circle within future receipt horizon; review lead only. No source-to-FIRMS event ID join."
            })
        lead_rows.sort(key=lambda a:(a["agency_provider"],a["official_id"]))
        all_cases.extend(lead_rows)
        if len(all_cases)>MAX_LEADS:
            raise ValueError("agency source candidate review population exceeds 2000 leads")
        counts["candidate_agency_source_listings"]+=len(lead_rows)
        if lead_rows:counts["samples_with_review_leads"]+=1
        if any(x["post_decision_complete_receipts"]==0 for x in provider_health.values()):
            counts["samples_missing_agency_complete_source_receipts"]+=1
        counts["verified_positive_labels"]+=0
        counts["verified_negative_labels"]+=0
        # Store decision time separately from future candidate evidence.
        all_cases.append({
            "kind":"source_coverage_audit", "sample_id":sample["sample_id"],
            "decision_at":start, "outcome_window_end_exclusive":stop,
            "agency_evidence_available_through":effective_stop,
            "right_censored_by_evidence_cutoff":bool(effective_stop<stop),
            "providers":provider_health,
            "candidate_source_listings":len(lead_rows),
            "absence_implies_no_wildfire":False,
            "target_label":None,
            "model_training_allowed":False,
        })
        if len(all_cases)>MAX_LEADS+MAX_SAMPLES:
            raise ValueError("review population exceeds size budget")
    review=[r for r in all_cases if "review_lead_id" in r]
    audit=[r for r in all_cases if r.get("kind")=="source_coverage_audit"]
    assert all(r["independent_outcome_label"] is None for r in review)
    assert all(r["target_label"] is None for r in audit)
    return {"schema_version":1,
            "kind":"unadjudicated_prospective_agency_spatial_review_leads",
            "cohort_manifest_sha256":manifest_sha,
            "agency_source_model":"original_prospective_cwfis_and_nifc_wfigs_receipts",
            "proposed_target":f"independently_audited_event_in_{manifest['target_horizon_hours']}h",
            "sources":list(SOURCES),
            "review_leads":review,"source_coverage_audit":audit,
            "counts":dict(sorted(counts.items())),
            "verified_independent_fire_labels":0,
            "verified_negative_fire_labels":0,
            "verified_new_ignition_times":0,
            "source_point_within_circle_not_identity_equivalence":True,
            "fire_probability":None,
            "model_training_allowed":False,
            "warnings":[
                "This is a provider-specific source listing review, NOT independent physical wildfire validation.",
                "Geodesic point-in-circle does not prove a fire perimeter overlaps the circle or FIRMS detections belong to one fire.",
                "First listing in available receipts is not ignition; left censoring and source publication lag remain unknown.",
                "An agency source outage or missing record is NOT a negative fire label.",
                "Capture after decision is FUTURE review evidence and must not be used as a contemporaneous prediction feature.",
                "No outcome labels or probability scores may be derived without separately audited source/event identity, observation opportunities and negative coverage.",
            ]}


def export_review(report: dict, destination: Path) -> dict:
    destination=Path(destination)
    if (destination.exists() or destination.is_symlink() or
        not destination.parent.is_dir() or destination.resolve().is_relative_to(ROOT)):
        raise ValueError("new private agency review output required outside Git checkout")
    overview={
        "schema_version":1,"kind":report["kind"],
        "cohort_manifest_sha256":report["cohort_manifest_sha256"],
        "counts":report["counts"],
        "verified_independent_fire_labels":0,
        "verified_negative_fire_labels":0,
        "model_training_allowed":False,
        "warnings":report["warnings"]
    }
    leads=b"".join(_canonical(row) for row in report["review_leads"])
    audit=b"".join(_canonical(row) for row in report["source_coverage_audit"])
    head="""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agency evidence review: unlabeled spatial leads</title>
<style>body{font:15px system-ui,sans-serif;max-width:980px;margin:24px auto;padding:16px;
background:#101f27;color:#eaf5f5;line-height:1.5}
section{border:1px solid #45636d;border-radius:8px;padding:16px;margin:12px 0}
table{width:100%;border-collapse:collapse}th,td{padding:8px;text-align:left;border-bottom:1px solid #42636a}
.muted{color:#bed0d6}code{overflow-wrap:anywhere}</style></head><body><main>
<h1>Prospective agency source listing review</h1>
<p class="muted">Geographic and time-adjacent SOURCE LEADS ONLY; no independent
wildfire/nonfire labels and no retrospective predictor leakage.</p>
<section><h2>Research evidence audit</h2><p>Region/time samples: """+str(len(report["source_coverage_audit"]))+"""
 · Agency listing review leads: """+str(len(report["review_leads"]))+"""
 · Independent validated labels: 0</p></section>
<section><h2>Sample coverage</h2><table><thead><tr><th>Sample</th><th>Agency listing leads</th>
<th>Missing source completion?</th><th>Future horizon censored?</th></tr></thead><tbody>"""
    entries=[]
    for record in report["source_coverage_audit"]:
        missing=any(x["post_decision_complete_receipts"]==0 for x in record["providers"].values())
        entries.append("<tr><td><code>"+escape(record["sample_id"])+"</code></td><td>"+
                       str(record["candidate_source_listings"])+"</td><td>"+str(missing)+
                       "</td><td>"+str(record["right_censored_by_evidence_cutoff"])+"</td></tr>")
    tail="""</tbody></table></section><p class="muted">All original source IDs,
times and SHA-256 proofs are in agency-review-leads.jsonl. This report makes no
fire/no-fire, new-ignition, burned-area or model-accuracy claims.</p>
</main></body></html>\n"""
    files={
        "agency-review-leads.jsonl":leads,
        "agency-source-coverage.jsonl":audit,
        "review.html":(head+"".join(entries)+tail).encode()
    }
    overview["files"]={name:{"sha256":hashlib.sha256(raw).hexdigest(),
                             "bytes":len(raw)} for name,raw in files.items()}
    files["manifest.json"]=_canonical(overview)
    if any(len(raw)>MAX_HTML_BYTES for raw in files.values()):
        raise ValueError("review export exceeds private output byte budget")
    destination.mkdir(mode=0o700)
    try:
        for name,raw in files.items():
            with (destination/name).open("xb") as output:
                os.fchmod(output.fileno(),0o600)
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
    except Exception:
        shutil.rmtree(destination)
        raise
    return {"review_leads":len(report["review_leads"]),
            "samples":len(report["source_coverage_audit"]),
            "independent_fire_labels":0,"negative_fire_labels":0,
            "file_names":sorted(files)}


def main():
    parser=argparse.ArgumentParser(description="Link independent original agency SOURCE listings to unlabeled historical FIRMS study decisions for private human review")
    parser.add_argument("--cohort-dir",type=Path,required=True)
    parser.add_argument("--agency-db",type=Path,required=True)
    parser.add_argument("--through",help="UTC-aware maximum known agency receipt time")
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args()
    report=build_agency_review_candidates(args.cohort_dir,args.agency_db,through=args.through)
    print(json.dumps(export_review(report,args.output_dir),sort_keys=True))


if __name__=="__main__":
    main()
