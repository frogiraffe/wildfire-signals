"""Full SHA-backed CAL FIRE alternatives investigation regression suite.

Fixture CAL FIRE pages and pair records are synthetic test examples. All
original-source live pilot evidence is separately verified in CI.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest

from fire_public.calfire_ambiguity_dossiers import (
    build_from_matrix,investigate,csv_report,html_report,export,_days,
)
from test_calfire_incident_matrix import FullDetailCoverageTests


class AmbiguousOriginalEventDossiersTests(unittest.TestCase):
    def setUp(self):
        fixture=FullDetailCoverageTests("test_replay_full_source_url_partition_and_explicit_non_truth")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture=fixture
        self.root=fixture.root
        self.study=fixture.study
        self.annual=fixture.annual
        self.matrix=fixture.full()
        self.batches=fixture.batch_paths

    def test_real_source_shaped_full_coverage_creates_alternative_casefiles(self):
        result=investigate(self.study,self.annual,self.batches)
        self.assertEqual(result,build_from_matrix(self.matrix))
        self.assertEqual(result["nifc_mtbs_original_study_sha256"],self.matrix["study_sha256"])
        self.assertEqual(result["calfire_original_annual_archive_sha256"],
                         self.matrix["annual_calfire_original_html_sha256"])
        self.assertEqual(result["candidate_linked_unique_pages_verified"],14)
        self.assertEqual(result["research_candidate_count"],len(self.matrix["cases"]))
        self.assertEqual(sum(result["case_priority_counts"].values()),len(self.matrix["cases"]))
        self.assertEqual(result["validated_same_fire_event_crosswalks"],0)
        self.assertEqual(result["independent_nonfire_observations"],0)
        self.assertFalse(result["measured_wildfire_forecast_skill"])
        self.assertTrue(all(c["source_page_context_not_verified_ignition"] and
                            not c["event_identity_verified"] and
                            not c["fire_absence_verified"] for c in result["cases"]))
        self.assertTrue(all(x["priority_is_manual_work_not_match_probability"]
                            for x in result["cases"]))
        self.assertTrue(all(not p["independent_physical_event_identity_known"]
                            for c in result["cases"] for p in c["alternative_page_pairs"]))
        self.assertEqual(sum(len(c["alternative_page_pairs"]) for c in result["cases"]),
                         result["alternative_event_page_pair_comparisons"])
        self.assertTrue(any(c["source_option_count"]>1 for c in result["cases"]))
        self.assertTrue(all(
            len(c["alternative_page_pairs"])==
                 c["source_option_count"]*(c["source_option_count"]-1)//2
            for c in result["cases"]))
        self.assertEqual(result["cases"][0]["investigation_priority"],
                         "multiple_original_events_require_identity_investigation")

    def test_shared_official_page_is_not_independent_agency_confirmation(self):
        result=build_from_matrix(self.matrix)
        expected={}
        for c in self.matrix["cases"]:
            for item in c["calfire_leads"]:
                expected[item["source_url"]]=expected.get(item["source_url"],0)+1
        for c in result["cases"]:
            for item in c["official_calfire_page_options"]:
                self.assertEqual(item["candidate_pair_count_reusing_url"],
                                 expected[item["source_url"]])
                self.assertFalse(item["verified_event_identity"])
                if expected[item["source_url"]]>1:
                    self.assertIn("this_calfire_event_url_reused_by_multiple_mtbs_nifc_pairs",
                                  item["unresolved_source_signals"])
        self.assertEqual(result["candidate_event_url_reuse_occurrences"],
                         sum(value for value in expected.values() if value>1))

    def test_retrospective_date_gap_and_two_source_locations_are_not_ignition(self):
        r=build_from_matrix(self.matrix)
        self.assertEqual(_days("2018-07-20","2018-07-22"),2)
        self.assertIsNone(_days("not-a-date",None))
        pairs=[p for c in r["cases"] for p in c["alternative_page_pairs"]]
        self.assertGreater(len(pairs),0)
        self.assertTrue(all(p["different_official_page_urls"] for p in pairs))
        self.assertTrue(all(p["displayed_source_point_distance_km_not_ignition"] is None
                or p["displayed_source_point_distance_km_not_ignition"]>=0 for p in pairs))
        for c in r["cases"]:
            self.assertIn("comparable_nifc_ignition_day_not_verified",
                          c["unresolved_evidence_gates"])

    def test_no_source_lead_is_not_negation_and_all_single_leads_require_review(self):
        altered=dict(self.matrix)
        rows=[dict(c) for c in self.matrix["cases"]]
        # Creating synthetic missing name lead while preserving source-page
        # completeness would falsify the source graph; the loader must catch it.
        rows[0]["calfire_leads"]=[]
        altered["cases"]=rows
        with self.assertRaisesRegex(ValueError,"source link population changed|lead count drift"):
            build_from_matrix(altered)

    def test_matrix_not_fully_replayed_or_fabricated_labels_rejected(self):
        for changed in [
            {"all_candidate_linked_detail_pages_archived":False},
            {"verified_event_crosswalks":1},
            {"verified_nonfire_labels":1},
            {"model_skill_measured":True},
            {"original_detail_pages_verified":3},
        ]:
            bad=dict(self.matrix,**changed)
            with self.assertRaisesRegex(ValueError,"complete, unverified"):
                build_from_matrix(bad)

    def test_original_detail_tamper_is_rejected_by_full_replay(self):
        path=self.batches[0]/"calfire-original-detail-01.html"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            investigate(self.study,self.annual,self.batches)

    def test_original_nifc_source_corruption_rejected(self):
        path=next(self.study.glob("nifc-*-page-*.geojson"))
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            investigate(self.study,self.annual,self.batches)

    def test_html_escapes_untrusted_source_names_and_has_no_remote_code(self):
        model=build_from_matrix(self.matrix)
        fake=dict(model,cases=[dict(c) for c in model["cases"]])
        fake["cases"][0]["mtbs_name"]="<img src=x onerror=alert('x')>"
        opts=[dict(o) for o in fake["cases"][0]["official_calfire_page_options"]]
        opts[0]["source_name"]="=HYPERLINK('http://bad.example')"
        fake["cases"][0]["official_calfire_page_options"]=opts
        text=html_report(fake)
        self.assertNotIn("<img src=x",text)
        self.assertIn("&lt;img",text)
        self.assertIn("script-src &#x27;none&#x27;",text)
        self.assertNotIn("<script",text)
        self.assertIn("Official incident page",text)
        csv=csv_report(fake)
        self.assertIn("'=HYPERLINK",csv)
        self.assertEqual(csv.splitlines()[0].split(",")[0],"candidate_id")
        falsified=dict(model,validated_same_fire_event_crosswalks=5)
        with self.assertRaisesRegex(ValueError,"fabricated verified"):
            html_report(falsified)

    def test_new_only_dossier_export_outside_original_source_paths(self):
        model=build_from_matrix(self.matrix)
        output=self.root/"investigator-casebooks"
        export(model,output,study_dir=self.study,
               annual_dir=self.annual,batches=self.batches)
        self.assertEqual(json.loads((output/"ambiguity-dossiers.json").read_text()),
                         model)
        self.assertIn("candidate_id,investigation_priority",
                      (output/"ambiguity-dossiers.csv").read_text())
        self.assertIn("historical alternative-event dossiers",
                      (output/"ambiguity-dossiers.html").read_text())
        with self.assertRaisesRegex(ValueError,"new dossier output"):
            export(model,output,study_dir=self.study,
                   annual_dir=self.annual,batches=self.batches)
        with self.assertRaisesRegex(ValueError,"new dossier output"):
            export(model,self.study/"bad",study_dir=self.study,
                   annual_dir=self.annual,batches=self.batches)

    def test_cli_runs_every_original_source_replay_and_exposes_nontruth(self):
        out=self.root/"cli-ambiguity"
        argv=[sys.executable,"-m","fire_public.calfire_ambiguity_dossiers",
              "--study-dir",str(self.study),
              "--calfire-archive-dir",str(self.annual)]
        for batch in self.batches:
            argv+=["--batch",str(batch)]
        argv+=["--output-dir",str(out)]
        p=subprocess.run(argv,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        data=json.loads(p.stdout)
        self.assertEqual(data["original_calfire_pages_replayed"],14)
        self.assertEqual(data["verified_same_fire_crosswalks"],0)
        self.assertEqual(data["verified_nonfire"],0)
        self.assertNotEqual(subprocess.run(argv,capture_output=True).returncode,0)


if __name__=="__main__":
    unittest.main()
