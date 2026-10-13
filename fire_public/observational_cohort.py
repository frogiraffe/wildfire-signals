"""Leakage-aware observational cohort builder for future *independently labeled* studies.

Rows represent preregistered region/decision pairs, never physical wildfire
incidents. Source completeness is a collection audit, NOT orbital exposure.
All ground-truth labels are intentionally null. No model is trained.
"""
from __future__ import annotations

import argparse
import csv
from datetime import timedelta
from html import escape
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil

from .historical_signal_analysis import (
    _read_only, _utc, _valid_coordinate, analyze_historical_signals, WINDOWS)
from .region_diagnostics import distance_km

ROOT = Path(__file__).resolve().parents[1]
REGION_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,47}\Z")
MAX_REGIONS = 12
MAX_DECISIONS = 256
LOOKBACKS = (24, 48, 72, 168, 336)
CADENCES = (1, 2, 3, 4, 6, 12, 24)
TARGET_HORIZONS = (6, 12, 24, 48, 72)
FEATURE_NAMES = (
    "candidate_cell_hours", "unique_raw_pixels", "distinct_cells",
    "multi_sensor_cell_hours", "median_bin_cell_hours", "mad_bin_cell_hours",
    "theil_sen_cell_hours_per_hour", "later_minus_earlier_cell_hours",
    "capture_lag_hours_median"
)


def validate_regions(regions: list[dict]) -> list[dict]:
    """Freeze a nonoverlapping global sampling frame *before* outcome labeling."""
    if not isinstance(regions, list) or not 1 <= len(regions) <= MAX_REGIONS:
        raise ValueError("regions must contain 1..12 selected worldwide circles")
    seen = set()
    checked = []
    for region in regions:
        if not isinstance(region, dict) or set(region) != {
            "region_id","latitude","longitude","radius_km"
        } or not isinstance(region["region_id"], str) or not REGION_ID.fullmatch(region["region_id"]):
            raise ValueError("region requires stable ID and exact latitude/longitude/radius keys")
        rid = region["region_id"]
        if rid in seen:
            raise ValueError("duplicate analysis region ID")
        seen.add(rid)
        if (not _valid_coordinate(region["latitude"],-90,90) or
            not _valid_coordinate(region["longitude"],-180,180) or
            not _valid_coordinate(region["radius_km"],0.01,250)):
            raise ValueError("invalid analysis circle")
        checked.append({
            "region_id":rid, "latitude":float(region["latitude"]),
            "longitude":float(region["longitude"]),
            "radius_km":float(region["radius_km"])
        })
    # Overlap can leak the same raw thermal observations into "held out" regions.
    for i, first in enumerate(checked):
        for second in checked[i+1:]:
            gap = distance_km(first["latitude"], first["longitude"],
                              second["latitude"], second["longitude"])
            if gap <= first["radius_km"]+second["radius_km"]:
                raise ValueError("geodesic analysis regions overlap; use a disjoint sampling frame")
    return sorted(checked, key=lambda r:r["region_id"])


def _canonical(doc) -> bytes:
    return (json.dumps(doc,sort_keys=True,separators=(",",":"),
                       ensure_ascii=False,allow_nan=False)+"\n").encode()


def build_observational_cohort(
    pixel_db: str | Path, regions: list[dict], *, start_at: str, end_at: str,
    cadence_hours: int = 6, lookback_hours: int = 24, target_hours: int = 24,
    source: str = "all"
) -> dict:
    if (type(cadence_hours) is not int or cadence_hours not in CADENCES or
        type(lookback_hours) is not int or lookback_hours not in LOOKBACKS or
        type(target_hours) is not int or target_hours not in TARGET_HORIZONS):
        raise ValueError("invalid forecast horizon, feature lookback or decision cadence")
    if source not in ("all","VIIRS_NOAA20_NRT","VIIRS_NOAA21_NRT"):
        raise ValueError("unsupported original FIRMS observation source")
    chosen = validate_regions(regions)
    start, end = _utc(start_at), _utc(end_at)
    if end <= start or (end-start).total_seconds()% (cadence_hours*3600):
        raise ValueError("decision range must be positive and divisible by cadence")
    times = int((end-start).total_seconds()/(cadence_hours*3600))
    if times * len(chosen) > MAX_DECISIONS:
        raise ValueError("prospective cohort exceeds bounded 256 region/decision rows")
    if times < 1:
        raise ValueError("cohort has no decision timestamps")
    with _read_only(Path(pixel_db)) as db:
        last = db.execute("SELECT MAX(captured_at) FROM pixel_scans").fetchone()[0]
        first = db.execute("SELECT MIN(captured_at) FROM pixel_scans").fetchone()[0]
    if not last or end > _utc(last):
        raise ValueError("requested decisions must finish before the last original archived capture")
    rows = []
    for region in chosen:
        for index in range(times):
            decision = start+timedelta(hours=index*cadence_hours)
            cut = decision.isoformat()
            report = analyze_historical_signals(
                pixel_db, at=cut, hours=lookback_hours,
                latitude=region["latitude"], longitude=region["longitude"],
                radius_km=region["radius_km"], source=source)
            quality = report["bin_quality"]
            observed = report["summary"]
            complete = bool(quality["trend_descriptive_only_available"])
            # "usable" means adequate recorded collection requests for descriptive
            # analysis, NOT independently validated orbital/sensor availability.
            feature_values = ({
                "candidate_cell_hours":observed["distinct_candidate_cell_hours"],
                "unique_raw_pixels":observed["unique_raw_pixel_observations"],
                "distinct_cells":observed["distinct_cells_across_window"],
                "multi_sensor_cell_hours":observed["multi_sensor_cell_hours"],
                "median_bin_cell_hours":observed["median_bin_cell_hours"],
                "mad_bin_cell_hours":observed["mad_bin_cell_hours"],
                "theil_sen_cell_hours_per_hour":observed["theil_sen_cell_hours_per_hour"],
                "later_minus_earlier_cell_hours":observed["later_minus_earlier_cell_hours"],
                "capture_lag_hours_median":observed["capture_lag_hours_median"],
            } if complete else {key:None for key in FEATURE_NAMES})
            identity = hashlib.sha256(_canonical([
                region["region_id"],cut,lookback_hours,target_hours,source
            ])).hexdigest()[:24]
            rows.append({
                "sample_id":"signal-study-"+identity,
                "unit":"preselected_geodesic_region_at_decision_time_not_fire_event",
                "region_id":region["region_id"],
                "latitude":region["latitude"],"longitude":region["longitude"],
                "radius_km":region["radius_km"],
                "decision_at":cut,
                "feature_window_start_at":(decision-timedelta(hours=lookback_hours)).isoformat(),
                "feature_window_end_exclusive":cut,
                "outcome_window_start_at":cut,
                "outcome_window_end_exclusive":(decision+timedelta(hours=target_hours)).isoformat(),
                "selected_sources":report["selected_sources"],
                "collection_scan_receipts":report["scan_receipts"],
                "source_completed_bins":quality["bins_with_all_selected_sources_complete_receipts"],
                "source_missing_receipt_bins":quality["bins_with_no_receipt"],
                "collector_only_completeness":complete,
                "orbital_exposure_validated":False,
                "region_observation_completeness_validated":False,
                "sample_quality":(
                    "all_bins_have_completed_collection_requests_but_no_orbital_exposure"
                    if complete else "censored_by_missing_or_incomplete_source_receipts"),
                "observed_archive_subset":{
                    "candidate_cell_hours":observed["distinct_candidate_cell_hours"],
                    "unique_raw_pixels":observed["unique_raw_pixel_observations"],
                    "note":"Observed subset only; zeros are not no-fire examples."
                },
                "features":feature_values,
                "source_provenance_receipts_sha256":report["provenance_receipts_sha256"],
                "source_first_captured_no_later_than":cut,
                # Deliberately do not fabricate physical fire identities or
                # independent binary non-event examples from absence of pixels.
                "target_label":None,
                "target_label_available_at":None,
                "independent_label_source":None,
                "independent_label_source_id":None,
                "model_training_allowed":False,
                "model_training_blocker":"no_independently_validated_binary_positives_and_negatives_or_orbital_exposure",
                "split_assignment":"unassigned",
                "source_linkage_to_agency_fire":"not_asserted"
            })
    labels = sum(row["target_label"] is not None for row in rows)
    complete = sum(row["collector_only_completeness"] for row in rows)
    counts = {
        "rows":len(rows),
        "regions":len(chosen),
        "decision_times_per_region":times,
        "collector_request_audited_rows":complete,
        "censored_source_rows":len(rows)-complete,
        "rows_with_verified_satellite_overpass_exposure":0,
        "independently_labeled_positive_rows":0,
        "independently_labeled_negative_rows":0,
        "model_trainable_rows":0
    }
    assert labels == 0
    frame = {
        "schema_version":1,
        "kind":"unlabeled_prospective_satellite_observation_study_frame",
        "research_maturity":"experimental_no_independent_ground_truth",
        "start_at":start.isoformat(), "end_at":end.isoformat(),
        "earliest_imported_source_capture":first,
        "latest_imported_source_capture":last,
        "cadence_hours":cadence_hours,
        "lookback_hours":lookback_hours,
        "target_horizon_hours":target_hours,
        "selected_sources":[source] if source!="all" else [
            "VIIRS_NOAA20_NRT","VIIRS_NOAA21_NRT"],
        "sampling_regions":chosen,
        "sampling_frame_locked_before_labels":True,
        "overlapping_region_circles_allowed":False,
        "counts":counts,
        "no_negative_label_inferred_from_missing_detection":True,
        "no_trajectory_or_event_identity_claimed":True,
        "no_satellite_acquisition_denominator":True,
        "holdout_split_performed":False,
        "source":"verified_local_historical_original_FIRMS_pixel_sqlite",
        "source_sqlite_read_only":True,
        "warning":"Output is a label-free observational research frame, NOT training data or measured wildfire incidence."
    }
    return {"manifest":frame,"rows":rows}


def render_quality_html(cohort: dict) -> str:
    """No scripts, embedded raw pixel data, network calls or external resources."""
    frame = cohort["manifest"]
    cells = []
    for row in cohort["rows"]:
        sample = escape(row["sample_id"])
        when = escape(row["decision_at"])
        area = escape(row["region_id"])
        subset = row["observed_archive_subset"]["candidate_cell_hours"]
        quality = escape(row["sample_quality"])
        metrics = row["features"]["theil_sen_cell_hours_per_hour"]
        cells.append("<tr><th scope='row'>"+area+"</th><td>"+when+"</td><td>"+
                     str(subset)+"</td><td>"+str(row["source_completed_bins"])+
                     "/12</td><td>"+(escape(str(metrics)) if metrics is not None else "Unknown")+
                     "</td><td>"+quality+"</td><td>Unlabeled</td><td><code>"+sample+"</code></td></tr>")
    summary = frame["counts"]
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wildfire Signals — Unlabeled Historical Observation Cohort</title>
<style>
:root{color-scheme:dark;background:#0d1b24;color:#eef5f6;font:15px system-ui,sans-serif}
body{max-width:1200px;margin:28px auto;padding:0 18px;line-height:1.5}
p{max-width:920px}.muted{color:#b8cdda}
dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}
dl div{border:1px solid #41616b;border-radius:7px;padding:12px}
dd{margin:0;font-size:1.5rem;font-weight:bold;font-variant-numeric:tabular-nums}
dt{font-size:.88rem;color:#bed1d9}.scroll{overflow:auto}
table{width:100%;min-width:920px;border-collapse:collapse}
th,td{padding:8px;border-bottom:1px solid #35535f;text-align:left;font-size:.83rem}
code{font-size:.8rem;overflow-wrap:anywhere}
</style></head><body><main>
<h1>Unlabeled prospective observation study frame</h1>
<p class="muted">Historical NASA FIRMS thermal candidates, source-censored. NOT a wildfire occurrence or model training dataset.</p>
<dl><div><dt>Sampled region/decision rows</dt><dd>""" + str(summary["rows"]) + """</dd></div>
<div><dt>Collector-audited rows</dt><dd>""" + str(summary["collector_request_audited_rows"]) + """</dd></div>
<div><dt>Rows with missing source receipts</dt><dd>""" + str(summary["censored_source_rows"]) + """</dd></div>
<div><dt>Independent outcome labels</dt><dd>0</dd></div></dl>
<p>Expected target: independently audited future outcomes within """ +
        str(frame["target_horizon_hours"]) + """ hours, currently <strong>unknown for every row</strong>.
Completed collection requests are NOT confirmed VIIRS orbital coverage.</p>
<div class="scroll"><table><thead><tr><th scope="col">Region</th><th scope="col">Decision UTC</th>
<th scope="col">Observed archive cell-hours</th><th scope="col">Complete source bins</th>
<th scope="col">Descriptive slope</th><th scope="col">Quality</th>
<th scope="col">Target</th><th scope="col">Sample ID</th></tr></thead><tbody>""" +
        "".join(cells) + """</tbody></table></div>
<p class="muted">Archive provenance is included in the JSONL/manifest. No probability,
p-value, land denominator, fire absence or independent fire identity is inferred.</p>
</main></body></html>\n"""


def export_cohort(cohort: dict, destination: Path) -> dict:
    """Atomic private new-only local output; raw evidence stays in its original DB."""
    destination=Path(destination)
    if (destination.exists() or destination.is_symlink() or
        not destination.parent.is_dir() or destination.parent.is_symlink() or
        destination.resolve().is_relative_to(ROOT)):
        raise ValueError("new private cohort destination outside public checkout required")
    rows = cohort["rows"]
    data = b"".join(_canonical(row) for row in rows)
    summary = {**cohort["manifest"],
        "files":{"observations.jsonl":{"sha256":hashlib.sha256(data).hexdigest(),
                                        "rows":len(rows)}},
        "fit_performed":False}
    buffer=io.StringIO(newline="")
    writer=csv.DictWriter(buffer,fieldnames=[
        "sample_id","region_id","decision_at","latitude","longitude","radius_km",
        "lookback_hours","target_horizon_hours","collector_only_completeness",
        "source_completed_bins","source_missing_receipt_bins","sample_quality",
        "observed_archive_candidate_cell_hours",*FEATURE_NAMES,
        "target_label","model_training_allowed"
    ],lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({
            "sample_id":row["sample_id"],"region_id":row["region_id"],
            "decision_at":row["decision_at"],"latitude":row["latitude"],
            "longitude":row["longitude"],"radius_km":row["radius_km"],
            "lookback_hours":cohort["manifest"]["lookback_hours"],
            "target_horizon_hours":cohort["manifest"]["target_horizon_hours"],
            "collector_only_completeness":row["collector_only_completeness"],
            "source_completed_bins":row["source_completed_bins"],
            "source_missing_receipt_bins":row["source_missing_receipt_bins"],
            "sample_quality":row["sample_quality"],
            "observed_archive_candidate_cell_hours":row["observed_archive_subset"]["candidate_cell_hours"],
            **row["features"],"target_label":None,"model_training_allowed":False
        })
    exports={
        "observations.jsonl":data,
        "observations.csv":buffer.getvalue().encode(),
        "quality.html":render_quality_html(cohort).encode()
    }
    for name,payload in exports.items():
        summary["files"][name]={"sha256":hashlib.sha256(payload).hexdigest(),
                                "bytes":len(payload)}
    exports["manifest.json"]=_canonical(summary)
    destination.mkdir(mode=0o700)
    try:
        for name,payload in exports.items():
            path=destination/name
            with path.open("xb") as stream:
                os.fchmod(stream.fileno(),0o600)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
    except Exception:
        shutil.rmtree(destination)
        raise
    return {"output":str(destination),"rows":len(rows),
            "censored_source_rows":summary["counts"]["censored_source_rows"],
            "label_count":0,"files":sorted(exports),
            "manifest_sha256":hashlib.sha256(exports["manifest.json"]).hexdigest()}


def main():
    parser=argparse.ArgumentParser(description="Offline label-free geographically registered historical FIRMS study frame")
    parser.add_argument("--pixel-db",type=Path,required=True)
    parser.add_argument("--regions-json",type=Path,required=True)
    parser.add_argument("--start-at",required=True)
    parser.add_argument("--end-at",required=True)
    parser.add_argument("--cadence-hours",type=int,default=6,choices=CADENCES)
    parser.add_argument("--lookback-hours",type=int,default=24,choices=LOOKBACKS)
    parser.add_argument("--target-hours",type=int,default=24,choices=TARGET_HORIZONS)
    parser.add_argument("--source",default="all",choices=("all","VIIRS_NOAA20_NRT","VIIRS_NOAA21_NRT"))
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args()
    if args.regions_json.is_symlink() or not args.regions_json.is_file() or args.regions_json.stat().st_size>32*1024:
        parser.error("a bounded local JSON list of regions is required")
    regions=json.loads(args.regions_json.read_text(encoding="utf-8"))
    result=build_observational_cohort(args.pixel_db,regions,
        start_at=args.start_at,end_at=args.end_at,
        cadence_hours=args.cadence_hours,lookback_hours=args.lookback_hours,
        target_hours=args.target_hours,source=args.source)
    print(json.dumps(export_cohort(result,args.output_dir),sort_keys=True))


if __name__=="__main__":
    main()
