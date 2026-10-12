"""Reproducible, fail-closed evaluation of independently labeled wildfire outcomes.

This does not create labels from FIRMS, active agency layer absence or proximity.
A human-reviewed cohort manifest explicitly declares the target, horizon,
sampling and negative-label verification. No live API calls are made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .historical_baseline import historical_rate_experiment
from .evaluation_splits import holdout_split
from .model_evaluation import evaluate_binary
from .history import _timestamp

MAX_ROWS = 100_000
MAX_BYTES = 64 * 1024 * 1024
REQUIRED_MANIFEST = ("schema_version", "target_name", "target_definition",
    "horizon_hours", "unit_of_analysis", "study_region", "labeling_protocol",
    "positive_label_rule", "negative_label_rule", "sampling_frame",
    "negative_coverage_audited", "independent_label_provenance_verified",
    "ground_truth_source_url", "rights_url", "prepared_by", "prepared_at")


def _read_json(path: Path, cap: int = MAX_BYTES) -> Any:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > cap:
        raise ValueError(f"input missing, symbolic, or exceeds size budget: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _manifest(data: dict) -> None:
    if not isinstance(data, dict) or any(key not in data for key in REQUIRED_MANIFEST):
        raise ValueError("complete independently labeled cohort manifest required")
    if data["schema_version"] != 1:
        raise ValueError("unsupported manifest schema")
    for key in ("target_name","target_definition","unit_of_analysis","study_region",
                "labeling_protocol","positive_label_rule","negative_label_rule",
                "sampling_frame","prepared_by"):
        if not isinstance(data[key], str) or len(data[key].strip()) < 8:
            raise ValueError(f"manifest requires meaningful {key}")
    if (type(data["horizon_hours"]) not in (int, float)
            or not math.isfinite(data["horizon_hours"])
            or not 0 < data["horizon_hours"] <= 24 * 365):
        raise ValueError("bounded explicit prediction horizon required")
    for key in ("negative_coverage_audited","independent_label_provenance_verified"):
        if data[key] is not True:
            raise ValueError(f"{key} must be explicitly audited and true")
    for key in ("ground_truth_source_url","rights_url"):
        if not isinstance(data[key],str) or not data[key].startswith("https://"):
            raise ValueError(f"trusted provenance URL required: {key}")
    _timestamp(data["prepared_at"])
    forbidden = ("firms", "thermal detection", "missing from active", "disappeared")
    # A name is not adequate validation but reject explicit use of known unsafe
    # negative or pseudo-ground-truth rules.
    for key in ("positive_label_rule","negative_label_rule"):
        if any(t in data[key].casefold() for t in forbidden):
            raise ValueError("satellite detection or agency disappearance is not independent ground truth")


def _read_cohort(path: Path) -> tuple[list[dict], str]:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
        raise ValueError("cohort JSONL file unavailable or too large")
    digest = hashlib.sha256()
    items = []
    with path.open("rb") as handle:
        for line in handle:
            digest.update(line)
            if len(line) > 32 * 1024:
                raise ValueError("JSONL row exceeds size limit")
            if not line.strip():
                continue
            if len(items) >= MAX_ROWS:
                raise ValueError("cohort row count exceeds limit")
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError("cohort row must be an object")
            items.append(obj)
    return items, digest.hexdigest()


def _audit_rows(rows: list[dict], manifest: dict) -> dict:
    required = ("event_id","region_id","decision_at","label_available_at",
                "label","label_source","label_source_id","label_evidence_url",
                "label_verified_at","feature_cutoff_at","case_sampling_id")
    events, sampling = set(), set()
    counts = Counter()
    for i,r in enumerate(rows):
        missing = [field for field in required if field not in r]
        if missing:
            raise ValueError(f"row {i}: missing required fields {', '.join(missing)}")
        if type(r["label"]) is not int or r["label"] not in (0,1):
            raise ValueError(f"row {i}: independent binary label 0/1 required")
        if any(not isinstance(r[key],str) or not r[key].strip() for key in
               ("event_id","region_id","label_source","label_source_id","case_sampling_id")):
            raise ValueError(f"row {i}: missing event, region, label source or sampling identity")
        if (not isinstance(r["label_evidence_url"],str) or
                not r["label_evidence_url"].startswith("https://")):
            raise ValueError(f"row {i}: independent label evidence URL required")
        decision = _timestamp(r["decision_at"])
        features = _timestamp(r["feature_cutoff_at"])
        available = _timestamp(r["label_available_at"])
        reviewed = _timestamp(r["label_verified_at"])
        if features > decision:
            raise ValueError(f"row {i}: feature-time leakage after decision")
        if available <= decision or reviewed < available:
            raise ValueError(f"row {i}: invalid independent label acquisition chronology")
        horizon = (datetime.fromisoformat(available) -
                   datetime.fromisoformat(decision)).total_seconds()/3600
        if horizon < 0:
            raise ValueError("invalid observation horizon")
        pair=(r["event_id"],decision)
        if pair in events:
            raise ValueError(f"row {i}: duplicate decision event")
        events.add(pair)
        sample=(r["case_sampling_id"],decision)
        if sample in sampling:
            raise ValueError(f"row {i}: duplicate case sampling identity")
        sampling.add(sample)
        if r.get("label_source") in ("firms","satellite_candidate"):
            raise ValueError(f"row {i}: satellite pixels cannot supply independent wildfire labels")
        counts[str(r["label"])] += 1
    if not rows:
        raise ValueError("cohort must not be empty")
    return {"n":len(rows),"positive":counts["1"],"negative":counts["0"],
            "distinct_events":len({r["event_id"] for r in rows}),
            "distinct_regions":len({r["region_id"] for r in rows})}


def run_evaluation(cohort: Path, manifest_path: Path, *,
                   test_start: str, embargo_hours: float = 168,
                   heldout_regions: tuple[str,...] = (),
                   smoothing: float = 1.0) -> dict:
    manifest = _read_json(manifest_path, 1024 * 1024)
    _manifest(manifest)
    rows, sha = _read_cohort(cohort)
    audit = _audit_rows(rows,manifest)
    if audit["positive"]==0 or audit["negative"]==0:
        raise ValueError("both independently verified positive and negative cases required")
    result=historical_rate_experiment(rows,test_start=test_start,
        embargo_hours=embargo_hours,heldout_regions=heldout_regions,
        smoothing=smoothing)
    # The exact cohort and source manifest bytes allow independently repeating
    # the experiment without ever embedding identifiable case rows in outputs.
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return {
        "schema_version":1,"cohort_sha256":sha,"manifest_sha256":manifest_sha,
        "label_audit":audit,"target":{"name":manifest["target_name"],
            "definition":manifest["target_definition"],
            "horizon_hours":manifest["horizon_hours"],
            "unit_of_analysis":manifest["unit_of_analysis"],
            "study_region":manifest["study_region"]},
        "ground_truth_provenance":{
            "source":manifest["ground_truth_source_url"],"rights":manifest["rights_url"],
            "negative_coverage_audited":True,
            "independent_label_provenance_verified":True,
            "protocol":manifest["labeling_protocol"]},
        "experiment":result,
        "scientific_status":"audited_input_baseline_not_independently_revalidated",
        "caveats":[
            "Manifest declarations and label URLs are checked, not independently verified by this script.",
            "No satellite thermal detections or active-layer disappearances are converted into wildfire labels.",
            "Feature time cutoffs are checked but original weather/remote sensing data issue times still need source audit.",
            "A constant global base rate is an experimental comparator, not a calibrated regional fire forecast.",
            "Do not present held-out fixture scores as real-world model skill."
        ],
    }


def main() -> None:
    parser=argparse.ArgumentParser(description="Evaluate independently sourced binary wildfire outcomes")
    parser.add_argument("--cohort",type=Path,required=True,help="Private audited JSONL cohort")
    parser.add_argument("--manifest",type=Path,required=True,help="Explicit target/negative sampling protocol")
    parser.add_argument("--test-start",required=True,help="UTC split start")
    parser.add_argument("--embargo-hours",type=float,default=168)
    parser.add_argument("--heldout-region",action="append",default=[])
    parser.add_argument("--smoothing",type=float,default=1.0)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    paths={p.resolve() for p in (args.cohort,args.manifest)}
    if args.output.resolve() in paths:
        parser.error("cannot overwrite an input cohort or manifest")
    if args.output.exists():
        parser.error("output already exists")
    result=run_evaluation(args.cohort,args.manifest,test_start=args.test_start,
        embargo_hours=args.embargo_hours,heldout_regions=tuple(args.heldout_region),
        smoothing=args.smoothing)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2,ensure_ascii=False,sort_keys=True)
        f.write("\n")
    print(json.dumps({"output":str(args.output),"train":result["experiment"]["train_n"],
        "test":result["experiment"]["test_n"],
        "scientific_status":result["scientific_status"]},sort_keys=True))


if __name__=="__main__":
    main()
