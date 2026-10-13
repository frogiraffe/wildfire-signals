"""Reproduce complete candidate URL coverage using synthetic original source pages.

Separate real CI exercises all government providers. This suite never claims
a synthetic incident is a verified fire, negative or same-incident crosswalk.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import unittest

from fire_public.calfire_incident_archive import compare,save as save_annual
from fire_public.calfire_incident_details import (
    capture,save as save_batch, select_leads
)
from fire_public.calfire_incident_matrix import analyze,as_html,as_csv,write_reports
from test_calfire_incident_details import OriginalDetailPageTests,detail
from test_calfire_incident_archive import html_archive


class FullDetailCoverageTests(unittest.TestCase):
    def setUp(self):
        f=OriginalDetailPageTests("test_selected_original_links_are_bounded_deterministic_and_not_a_census")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.fx=f
        self.root=f.root
        self.study=f.study
        self.annual=self.root/"all-calfire-source"
        # Exactly 14 *synthetic* distinct URLs with source-name tokens so we
        # can regression-test multiple batches and incomplete final batch.
        self.annual_raw=html_archive().replace(b"Unrelated report",b"Fire record")
        self.annual_report=compare(self.study,self.annual_raw,
                                   captured_at="2026-10-13T12:00:00Z")
        save_annual(self.annual,self.annual_raw,self.annual_report)
        self.urls={link["calfire_event_url"] for case in self.annual_report["cases"]
                   for link in case["calfire_name_only_leads"]}
        self.assertEqual(len(self.urls),14)
        self.selected_seed="matrix-fixture-v1"
        self.batch_paths=[]

    def provider(self,url):
        name=next(link["calfire_name"] for row in self.annual_report["cases"]
                  for link in row["calfire_name_only_leads"]
                  if link["calfire_event_url"]==url)
        return detail(name=name)

    def make_batch(self,offset,max_pages=6,seed=None):
        args=dict(max_pages=max_pages,offset=offset,seed=seed or self.selected_seed,
                  get=self.provider,clock=lambda:"2026-10-13T14:00:00Z")
        report,source=capture(self.study,self.annual,**args)
        output=self.root/("pages-"+str(len(self.batch_paths))+"-"+str(offset))
        save_batch(output,report,source)
        self.batch_paths.append(output)
        return report,output

    def full(self):
        self.make_batch(0)
        self.make_batch(6)
        self.make_batch(12)
        return analyze(self.study,self.annual,self.batch_paths)

    def test_replay_full_source_url_partition_and_explicit_non_truth(self):
        result=self.full()
        self.assertEqual(result["original_detail_pages_verified"],14)
        self.assertEqual(result["candidate_linked_unique_calfire_urls"],14)
        self.assertEqual(result["original_detail_page_batch_count"],3)
        self.assertEqual(result["original_candidate_count"],len(self.annual_report["cases"]))
        self.assertTrue(result["all_candidate_linked_detail_pages_archived"])
        self.assertEqual(result["verified_event_crosswalks"],0)
        self.assertEqual(result["verified_nonfire_labels"],0)
        self.assertFalse(result["model_skill_measured"])
        self.assertEqual(len(result["selected_source_evidence_files"]),14)
        self.assertEqual(sum(result["candidate_outcomes"].values()),result["original_candidate_count"])
        self.assertTrue(all(not case["verified_same_fire_event"] for case in result["cases"]))
        self.assertTrue(all(not lead["same_fire_verified"]
                            for case in result["cases"] for lead in case["calfire_leads"]))
        self.assertGreater(sum(x["calfire_lead_count"] for x in result["cases"]),14)
        self.assertEqual(result["source_study_sha256"] if "source_study_sha256" in result else result["study_sha256"],
                         self.fx.archive["nifc_mtbs_source_study_sha256"])

    def test_partial_source_page_coverage_fails_not_false_empty_outcomes(self):
        self.make_batch(0)
        self.make_batch(6)
        with self.assertRaisesRegex(ValueError,"coverage incomplete"):
            analyze(self.study,self.annual,self.batch_paths)

    def test_source_page_offsets_must_not_overlap_or_skip(self):
        self.make_batch(0)
        self.make_batch(0)
        self.make_batch(12)
        with self.assertRaisesRegex(ValueError,"duplicate"):
            analyze(self.study,self.annual,self.batch_paths)

    def test_source_selection_seed_conflicts_rejected(self):
        self.make_batch(0)
        self.make_batch(6,seed="different-selection-seed")
        self.make_batch(12)
        with self.assertRaisesRegex(ValueError,"different deterministic|coverage incomplete|duplicate"):
            analyze(self.study,self.annual,self.batch_paths)

    def test_source_page_tampering_rejected_before_matrix(self):
        self.make_batch(0)
        self.make_batch(6)
        self.make_batch(12)
        path=self.batch_paths[1]/"calfire-original-detail-01.html"
        path.write_bytes(path.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            analyze(self.study,self.annual,self.batch_paths)

    def test_source_metadata_tampering_and_original_archive_drift_detected(self):
        self.make_batch(0)
        self.make_batch(6)
        self.make_batch(12)
        reportfile=self.batch_paths[2]/"detail-study.json"
        raw=json.loads(reportfile.read_text())
        raw["pages"][0]["source_name"]="Fake provider event"
        reportfile.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,"differs from archived"):
            analyze(self.study,self.annual,self.batch_paths)

    def test_report_html_csv_sanitization_and_three_new_only_files(self):
        report=self.full()
        html=as_html(report)
        self.assertIn("Content-Security-Policy",html)
        self.assertIn("script-src &#x27;none&#x27;",html)
        self.assertNotIn("<script",html)
        self.assertIn("Official incident page",html)
        csv=as_csv(report)
        self.assertIn("candidate_id,work_status",csv)
        fake=dict(report,cases=[dict(report["cases"][0])])
        fake["cases"][0]["mtbs_name"]='=HYPERLINK("https://malicious.example")'
        self.assertIn("'=HYPERLINK",as_csv(fake))
        fake["cases"][0]["mtbs_name"]='<img src=x onerror=alert("xss")>'
        self.assertNotIn("<img src=x",as_html(fake))
        self.assertIn("&lt;img",as_html(fake))
        out=self.root/"matrix"
        a,b,c=out/"matrix.json",out/"matrix.csv",out/"matrix.html"
        write_reports(report,a,b,c,study_dir=self.study,
                      archive_dir=self.annual,batches=self.batch_paths)
        self.assertEqual(json.loads(a.read_text())["original_detail_pages_verified"],14)
        with self.assertRaisesRegex(ValueError,"must be new"):
            write_reports(report,a,b,c,study_dir=self.study,
                          archive_dir=self.annual,batches=self.batch_paths)

    def test_cli_full_source_replay_and_exclusive_file_exports(self):
        self.full()
        dest=self.root/"cli"
        a,b,c=dest/"report.json",dest/"report.csv",dest/"report.html"
        command=[sys.executable,"-m","fire_public.calfire_incident_matrix",
                 "--study-dir",str(self.study),
                 "--calfire-archive-dir",str(self.annual)]
        for batch in self.batch_paths:
            command+=["--batch",str(batch)]
        command+=["--json",str(a),"--csv",str(b),"--html",str(c)]
        p=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)["authentic_original_detail_urls"],14)
        self.assertEqual(json.loads(a.read_text())["verified_nonfire_labels"],0)
        self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)

    def test_offset_selection_invalid_and_beyond_source_list_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"offset"):
            select_leads(self.annual_report,6,seed=self.selected_seed,offset=-1)
        with self.assertRaisesRegex(ValueError,"beyond"):
            select_leads(self.annual_report,6,seed=self.selected_seed,offset=14)
        with self.assertRaisesRegex(ValueError,"offset"):
            select_leads(self.annual_report,6,seed=self.selected_seed,offset=True)


if __name__=="__main__":
    unittest.main()
