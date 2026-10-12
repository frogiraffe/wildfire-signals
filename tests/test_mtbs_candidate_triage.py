"""NIFC–MTBS research work triage, including truly byte-backed provider fixture.

These are synthetic provider records and fake reviewer dispositions, not
verified ground truth, model predictions, or real incident crosswalks.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from fire_public.mtbs_candidate_triage import (
    _csv_safe, _name_relation, analyze, to_csv, to_html,
)
from test_mtbs_match_review import PairReviewTests
from test_mtbs_pair_reconcile import PairReconciliationTests


class ResearchTriageTests(unittest.TestCase):
    def setUp(self):
        fixture=PairReviewTests("test_source_verified_packet_and_original_identity")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture=fixture
        self.root=fixture.root
        self.study=fixture.study

    def test_byte_verified_study_without_real_humans_is_work_queue_not_ground_truth(self):
        result=analyze(self.study)
        self.assertEqual(result["status"],
                         "retrospective_human_work_queue_not_fire_event_matching")
        self.assertEqual(result["source_bundle_sha256"],
                         hashlib.sha256((self.study/"aligned-study.json").read_bytes()).hexdigest())
        self.assertEqual(result["candidate_count"],len(self.fixture.report["candidate_pairs"]))
        self.assertEqual(sum(result["work_priorities"].values()),result["candidate_count"])
        self.assertFalse(result["human_review_inputs_provided"])
        self.assertEqual(result["review_vote_sha256s"],[])
        self.assertEqual(result["ground_truth_identity_verified"],0)
        self.assertEqual(result["independent_nonfire_labels_created"],0)
        self.assertFalse(result["prediction_accuracy_measured"])
        self.assertEqual(result["source_population"]["nifc_roi_published_object_ids"],3)
        self.assertEqual(result["source_population"]["mtbs_roi_published_object_ids"],2)
        self.assertTrue(all(x["review_status"]=="not_reviewed" for x in result["candidates"]))
        self.assertTrue(all(x["same_fire_event_verified"] is False for x in result["candidates"]))
        self.assertTrue(all(x["independent_outcome_verified"] is False for x in result["candidates"]))
        self.assertEqual(
            [x["candidate_id"] for x in result["candidates"]],
            sorted(x["candidate_id"] for x in result["candidates"]))
        self.assertTrue(all("comparable_nifc_ignition_date_not_established" in
                            x["source_review_flags"] for x in result["candidates"]))
        self.assertTrue(any(x["mtbs_candidate_degree"]>1 for x in result["candidates"]))
        self.assertTrue(any(x["nifc_candidate_degree"]>1 for x in result["candidates"]))

    def test_manual_reconciliation_changes_work_priority_not_verification(self):
        f=PairReconciliationTests("test_all_dispositions_correct_and_never_ground_truth")
        f.setUp()
        self.addCleanup(f.doCleanups)
        f._fill()
        result=analyze(f.study,f.first,f.second)
        self.assertTrue(result["human_review_inputs_provided"])
        self.assertEqual(len(result["review_vote_sha256s"]),2)
        self.assertEqual(result["review_status_counts"]["conflicting_hypotheses"],1)
        conflicting=[x for x in result["candidates"]
                     if x["review_status"]=="conflicting_hypotheses"]
        self.assertEqual(len(conflicting),1)
        self.assertEqual(conflicting[0]["priority"],"unresolved_review_conflict")
        self.assertEqual(result["ground_truth_identity_verified"],0)
        self.assertEqual(result["independent_nonfire_labels_created"],0)
        self.assertTrue(all(x["same_fire_event_verified"] is False
                            for x in result["candidates"]))

    def test_reviewers_must_be_present_as_an_actual_pair(self):
        with self.assertRaisesRegex(ValueError,"both independent review files"):
            analyze(self.study,self.root/"researcher.json",None)

    def test_no_prescribed_burn_assumed_wildfire_or_negative(self):
        r=analyze(self.study)
        self.assertEqual(r["candidate_count"],6)
        selected=r["candidates"]
        for row in selected:
            self.assertEqual(row["mtbs_fire_type"],"Wildfire")
        self.assertEqual(r["independent_nonfire_labels_created"],0)
        self.assertTrue(all(x["priority_is_workload_not_match_probability"]
                            for x in selected))

    def test_normalization_is_unicode_aware_and_ignores_generic_fire_word(self):
        self.assertEqual(_name_relation("Çınar FIRE", "çınar incident"),
                         ("same_distinctive_tokens_not_event_identity",1.0))
        self.assertEqual(_name_relation("Fire", "Incident"),
                         ("not_comparable_distinctive_name",None))
        self.assertEqual(_name_relation("Pine Hill", "Pine Ridge"),
                         ("some_distinctive_tokens_shared",round(1/3,4)))
        self.assertEqual(_name_relation("Alpha Fire", "Beta Fire"),
                         ("no_distinctive_tokens_shared",0.0))
        self.assertEqual(_name_relation(None,"Beta"),("not_comparable_distinctive_name",None))

    def test_excel_spreadsheet_formula_injection_and_html_untrusted_text(self):
        for s in ('=HYPERLINK("https://bad.example")', '+cmd', '-1+1', '@SUM(1)',
                  '  =1+1', '\t=1+1'):
            self.assertTrue(_csv_safe(s).startswith("'"))
        self.assertEqual(_csv_safe("Normal Fire"),"Normal Fire")
        study=analyze(self.study)
        injected=dict(study)
        forged=[dict(c) for c in study["candidates"]]
        forged[0]["mtbs_name"]="<img src=x onerror=alert('bad')>"
        forged[0]["nifc_name"]='=HYPERLINK("http://bad.test")'
        injected["candidates"]=forged
        page=to_html(injected)
        self.assertNotIn("<img src=x",page)
        self.assertIn("&lt;img src=x",page)
        self.assertIn("script-src &#x27;none&#x27;",page)
        self.assertNotIn("<script",page)
        self.assertIn("not fire-event",page)
        text=to_csv(injected)
        self.assertIn("'=HYPERLINK",text)

    def test_tampered_report_or_original_service_response_rejected(self):
        path=self.study/"aligned-study.json"
        report=json.loads(path.read_text())
        report["nifc_polygons"][0]["name"]="FAKE PROVIDER"
        path.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError,"NIFC selected source properties"):
            analyze(self.study)
        self.fixture.report["nifc_polygons"][0]["name"]=self.fixture.report["nifc_polygons"][0]["original_attributes"]["INCIDENT"]
        # Restore original source study via fixture-owned bytes after failing.
        from fire_public.mtbs_region_study import write_capture
        old=self.study
        recovered=self.root/"clean-again"
        write_capture(recovered,self.fixture.report,self.fixture.raw)
        source=next(recovered.glob("mtbs-*-roi-points.json"))
        source.write_bytes(source.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            analyze(recovered)

    def test_cli_exports_json_csv_html_and_refuses_overwrites(self):
        dest=self.root/"coordinator"
        json_out=dest/"work.json"
        csv_out=dest/"work.csv"
        html_out=dest/"work.html"
        command=[sys.executable,"-m","fire_public.mtbs_candidate_triage",
                 "--study-dir",str(self.study),
                 "--json",str(json_out),"--csv",str(csv_out),
                 "--html",str(html_out)]
        proc=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        output=json.loads(json_out.read_text())
        self.assertEqual(output["candidate_count"],6)
        self.assertEqual(output["ground_truth_identity_verified"],0)
        self.assertIn("candidate_id,priority",csv_out.read_text())
        self.assertIn("retrospective",html_out.read_text().lower())
        self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)
        bad=list(command)
        bad[-1]=str(self.study/"bad-output.html")
        self.assertNotEqual(subprocess.run(bad,capture_output=True).returncode,0)


if __name__=="__main__":
    unittest.main()
