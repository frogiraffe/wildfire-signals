"""End-to-end safety and reproducibility tests for independent label review.

Only the ArcGIS transport is mocked. Genuine official importer SQLite,
authentic sampled-source checksum checks and the real evaluation code execute.
No fixture outputs are real-world wildfire skill metrics.
"""
from __future__ import annotations
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fire_public.official_perimeters import sync_year
from fire_public.label_review import prepare_queue, finalize_queue
from fire_public.labeled_evaluation import run_evaluation

VERIFIED="2026-10-12T13:00:00Z"
AT="2026-10-13T00:00:00Z"

FRAME={
  "schema_version":1,
  "frame_name":"Externally enumerated test area-time units",
  "sampling_protocol":"Review every independently sampled location-day in testing",
  "frame_provenance":"Fixture-only source, not a validated real region-time sampling frame",
  "source_url":"https://example.org/independent-frame",
  "rights_url":"https://example.org/rights",
  "units":[
    {"sampling_unit_id":"control-2017","region_id":"region-2017",
     "latitude":37.0,"longitude":-120.0,"decision_at":"2017-07-05T00:00:00Z"},
    {"sampling_unit_id":"control-2018","region_id":"region-2018",
     "latitude":37.0,"longitude":-119.0,"decision_at":"2018-07-05T00:00:00Z"},
  ],
}

PROTOCOL={
  "schema_version":1,
  "target_name":"Independently adjudicated wildfire in 24-hour study region",
  "target_definition":"Independent full-window adjudicated wildfire in defined region",
  "horizon_hours":24,
  "unit_of_analysis":"One independently sampled and inspected region-time case",
  "study_region":"Artificial fixture regions, not claimed country coverage",
  "labeling_protocol":"Two separate reviewers inspect independent primary evidence",
  "positive_label_rule":"Documented independent wildfire event inside declared horizon",
  "negative_label_rule":"Independently audited full-window incident register and no event",
  "sampling_frame":"Independent enumerated location-day sampling units verified for completeness",
  "negative_coverage_audited":True,
  "independent_label_provenance_verified":True,
  "ground_truth_source_url":"https://example.org/independent-registry",
  "rights_url":"https://example.org/source-rights",
  "prepared_by":"Fixture researcher",
  "prepared_at":"2026-10-13T00:00:00Z",
  "coverage_attested_by":"Independent fixture audit team",
  "coverage_attested_at":"2026-10-13T00:00:00Z",
  "coverage_evidence_url":"https://example.org/complete-coverage-audit",
}


def official(year):
    return {"type":"Feature",
        "properties":{"OBJECTID":year,"GlobalID":f"guid-{year}",
            "FIRE_YEAR_INT":year,"INCIDENT":f"Agency fire {year}",
            "GIS_ACRES":100.0,"SOURCE":"agency"},
        "geometry":{"type":"Polygon","coordinates":[[
            [-120.1,37.0],[-120,37.0],[-120,37.1],
            [-120.1,37.1],[-120.1,37.0]]]}}
        

def provider(params):
    year=provider.year
    if "where" in params:
        provider.year=int(params["where"].split("=")[-1])
        return {"objectIds":[provider.year]}
    return {"type":"FeatureCollection","features":[official(year)]}
provider.year=2017


def review(case, ordinal):
    official_case=case["kind"]=="retrospective_official_perimeter_review"
    year=(case["source_fire_year"] if official_case
          else int(case["sampling_unit_id"].split("-")[-1]))
    start=f"{year}-07-05T00:00:00Z"
    date_verified=f"{year}-08-01T00:00:00Z"
    reviewer=lambda role:{
        "reviewer_id":f"{role}-person-{ordinal}",
        "evidence_url":f"https://example.org/{role}/case-{ordinal}",
        "reviewed_at":VERIFIED,
        "agrees_with_label":True,
    }
    obj={
      "case_id":case["case_id"],"status":"adjudicated",
      "label":int(official_case),
      "event_id":f"incident-or-sampled-event-{ordinal}",
      "region_id":f"region-{year}",
      "decision_at":start,
      "feature_cutoff_at":start,
      "label_available_at":date_verified,
      "label_verified_at":VERIFIED,
      "label_source":"independent-official-fixture-registry",
      "label_source_id":f"external-{ordinal}",
      "label_evidence_url":f"https://example.org/outcomes/{ordinal}",
      "primary":reviewer("primary"),
      "secondary":reviewer("secondary"),
    }
    if official_case:
        obj["independently_verified_event_at"]=f"{year}-07-05T04:00:00Z"
    else:
        obj["negative_coverage"]={
          "registry_complete_for_unit_window":True,
          "start_at":f"{year}-07-04T00:00:00Z",
          "end_at":f"{year}-07-08T00:00:00Z",
          "coverage_reviewer_id":f"auditor-{ordinal}",
          "reviewed_at":VERIFIED,
          "completeness_evidence_url":f"https://example.org/coverage/{ordinal}",
        }
    return obj


class LabelReviewTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.db=self.root/"official.sqlite3"
        self.frame=self.root/"frame.json"
        self.frame.write_text(json.dumps(FRAME),encoding="utf-8")
        self.queue_file=self.root/"review-queue.json"
        self.reviews_file=self.root/"reviews.json"
        self.protocol_file=self.root/"protocol.json"
        self.protocol_file.write_text(json.dumps(PROTOCOL),encoding="utf-8")
        for year in [2017,2018]:
            sync_year(self.db,year=year,max_records=1,
                      clock=lambda:AT,get_json=provider,
                      selection_mode="hash",selection_seed="review-fixture")
        self.queue=prepare_queue(self.db,at=AT,years=[2017,2018],
                                 frame_path=self.frame,max_controls=2)
        self.queue_file.write_text(json.dumps(self.queue),encoding="utf-8")
        self.decisions=[review(c,i) for i,c in enumerate(self.queue["cases"])]
        self.reviews={
          "schema_version":1,"queue_sha256":hashlib.sha256(
              self.queue_file.read_bytes()).hexdigest(),
          "decisions":self.decisions,
        }
        self.save_reviews()

    def save_reviews(self):
        self.reviews_file.write_text(json.dumps(self.reviews),encoding="utf-8")

    def finalize(self):
        self.save_reviews()
        return finalize_queue(self.queue_file,self.reviews_file,self.protocol_file)

    def test_real_sqlite_provenance_to_reviewed_cohort_and_baseline(self):
        self.assertEqual(self.queue["counts"]["official_perimeter_leads"],2)
        self.assertEqual(self.queue["counts"]["unlabeled_frame_units"],2)
        self.assertEqual(self.queue["negative_labels_created"],0)
        self.assertTrue(all(c["proposed_label"] is None for c in self.queue["cases"]))
        cases,manifest,status=self.finalize()
        self.assertEqual(len(cases),4)
        self.assertEqual(sum(x["label"] for x in cases),2)
        self.assertEqual(status["positive_labels"],2)
        self.assertEqual(status["negative_labels"],2)
        self.assertFalse(status["source_authenticity_externally_verified_by_tool"])
        self.assertEqual(manifest["review_queue_sha256"],
                         hashlib.sha256(self.queue_file.read_bytes()).hexdigest())
        cohort=self.root/"cohort.jsonl"
        manifest_path=self.root/"manifest.json"
        cohort.write_text("".join(json.dumps(x)+"\n" for x in cases))
        manifest_path.write_text(json.dumps(manifest))
        evaluation=run_evaluation(cohort,manifest_path,
                    test_start="2018-01-01T00:00:00Z",embargo_hours=168)
        self.assertEqual(evaluation["experiment"]["train_n"],2)
        self.assertEqual(evaluation["experiment"]["test_n"],2)
        self.assertEqual(evaluation["experiment"]["fit_rate"],0.5)
        self.assertEqual(evaluation["label_audit"]["negative"],2)
        self.assertEqual(evaluation["scientific_status"],
                         "audited_input_baseline_not_independently_revalidated")

    def test_synthetic_frame_is_not_prelabelled_no_fire(self):
        self.assertEqual(len([c for c in self.queue["cases"]
            if c["kind"]=="independent_frame_review"]),2)
        self.assertEqual(self.queue["state"],"unadjudicated_review_queue")
        self.assertNotIn("label",self.queue["cases"][2])
        self.assertIn("independently",self.queue["warnings"][-1])

    def test_queue_and_frame_change_detection(self):
        self.reviews["queue_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"immutable source queue digest"):
            self.finalize()
        self.reviews["queue_sha256"]=hashlib.sha256(self.queue_file.read_bytes()).hexdigest()
        self.reviews["decisions"].pop()
        with self.assertRaisesRegex(ValueError,"every queued case"):
            self.finalize()

    def test_no_agency_perimeter_as_negative(self):
        self.decisions[0]["label"]=0
        with self.assertRaisesRegex(ValueError,"fire absence"):
            self.finalize()

    def test_negative_must_verify_entire_prediction_window(self):
        control=next(x for x in self.decisions if x["label"]==0)
        control["negative_coverage"]["registry_complete_for_unit_window"]=False
        with self.assertRaisesRegex(ValueError,"coverage cannot be inferred"):
            self.finalize()
        control["negative_coverage"]["registry_complete_for_unit_window"]=True
        control["negative_coverage"]["end_at"]="2017-07-05T01:00:00Z"
        with self.assertRaisesRegex(ValueError,"entire declared horizon"):
            self.finalize()

    def test_reviewers_are_independent_and_postdate_label_source(self):
        self.decisions[0]["secondary"]["reviewer_id"]=self.decisions[0]["primary"]["reviewer_id"]
        with self.assertRaisesRegex(ValueError,"two distinct"):
            self.finalize()
        self.decisions[0]["secondary"]["reviewer_id"]="another-person"
        self.decisions[0]["primary"]["reviewed_at"]="2017-07-05T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"chronology"):
            self.finalize()

    def test_negative_coverage_requires_different_third_reviewer(self):
        control=next(x for x in self.decisions if x["label"]==0)
        control["negative_coverage"]["coverage_reviewer_id"]=control["primary"]["reviewer_id"]
        with self.assertRaisesRegex(ValueError,"third reviewer"):
            self.finalize()

    def test_predated_2017_positive_not_valid_label_for_2017_future_day(self):
        case=self.decisions[0]
        case["independently_verified_event_at"]="2017-07-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"outside declared prediction horizon"):
            self.finalize()

    def test_mismatched_frame_region_and_decision_rejected(self):
        control=next(x for x in self.decisions if x["label"]==0)
        control["region_id"]="moved-region"
        with self.assertRaisesRegex(ValueError,"predefined region"):
            self.finalize()

    def test_missing_attestation_blocks_unsafe_cohort(self):
        for key in ("negative_coverage_audited","independent_label_provenance_verified"):
            protocol=dict(PROTOCOL,**{key:False})
            self.protocol_file.write_text(json.dumps(protocol))
            with self.assertRaisesRegex(ValueError,"attestations required"):
                self.finalize()
        self.protocol_file.write_text(json.dumps(PROTOCOL))

    def test_partially_unresolved_queue_explicitly_counted(self):
        case=self.decisions[0]
        case.clear();case.update({"case_id":self.queue["cases"][0]["case_id"],
            "status":"unresolved","reason":"Need further independent incident evidence"})
        # remaining one positive and two audited negatives
        rows,manifest,status=self.finalize()
        self.assertEqual(len(rows),3)
        self.assertEqual(status["unresolved"],1)
        self.assertEqual(status["positive_labels"],1)

    def test_cli_prepare_and_finalize_no_overwrite(self):
        queue_path=self.root/"new-queue.json"
        prepare_cmd=[sys.executable,"-m","fire_public.label_review","prepare",
            "--perimeter-db",str(self.db),"--frame",str(self.frame),
            "--year","2017","--year","2018","--at",AT,
            "--max-controls","2","--output",str(queue_path)]
        first=subprocess.run(prepare_cmd,capture_output=True,text=True)
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(json.loads(queue_path.read_text())["counts"]["unlabeled_frame_units"],2)
        self.assertNotEqual(subprocess.run(prepare_cmd,capture_output=True).returncode,0)
        self.save_reviews()
        result_paths=[self.root/x for x in ("cohort.jsonl","out-manifest.json","out-summary.json")]
        done_cmd=[sys.executable,"-m","fire_public.label_review","finalize",
            "--queue",str(self.queue_file),"--reviews",str(self.reviews_file),
            "--protocol",str(self.protocol_file),"--cohort",str(result_paths[0]),
            "--manifest",str(result_paths[1]),"--summary",str(result_paths[2])]
        done=subprocess.run(done_cmd,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual(len(result_paths[0].read_text().splitlines()),4)
        self.assertEqual(json.loads(result_paths[2].read_text())["negative_labels"],2)
        blocked=subprocess.run(done_cmd,capture_output=True,text=True)
        self.assertNotEqual(blocked.returncode,0)
        altered=done_cmd[:]
        altered[altered.index("--cohort")+1]=str(self.db)
        self.assertNotEqual(subprocess.run(altered,capture_output=True).returncode,0)


if __name__=="__main__":
    unittest.main()
