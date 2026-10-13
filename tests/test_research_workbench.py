"""Complete original-data replay workbench tests; fixture source pages are synthetic."""
from __future__ import annotations

import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

from fire_public.calfire_ambiguity_dossiers import build_from_matrix
from fire_public.calfire_blind_review import packet
from fire_public.calfire_lineage_audit import analyze as lineage_audit
from fire_public.research_workbench import queue, csv_queue, offline_html
from test_calfire_incident_matrix import FullDetailCoverageTests


class WorkbenchEndToEndTests(unittest.TestCase):
    def setUp(self):
        fixture = FullDetailCoverageTests("test_replay_full_source_url_partition_and_explicit_non_truth")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.study, self.annual = fixture.study, fixture.annual
        self.casebook = build_from_matrix(fixture.full())
        self.batches = fixture.batch_paths
        self.source_candidates = self.casebook["cases"]

    def filled(self, name):
        _, result = packet(self.casebook, name)
        for vote in result["votes"]:
            vote.update(reason="Original fire event identity has not been authenticated.",
                        reviewed_at="2026-10-13T17:00:00Z")
        return result

    def test_queue_keeps_all_source_candidates_not_only_multiple_page_cases(self):
        report = queue(self.casebook, lineage_audit(self.casebook))
        self.assertEqual(report["original_candidate_population"],
                         self.casebook["research_candidate_count"])
        self.assertEqual(len(report["rows"]), len(self.source_candidates))
        self.assertEqual(report["original_official_page_population"],
                         self.casebook["candidate_linked_unique_pages_verified"])
        self.assertEqual(report["ambiguous_original_candidates"],
                         sum(r["source_option_count"] > 1 for r in self.source_candidates))
        self.assertEqual(sum(report["manual_work_priority_counts"].values()),
                         len(report["rows"]))
        self.assertEqual({r["candidate_id"] for r in report["rows"]},
                         {r["candidate_id"] for r in self.source_candidates})
        self.assertEqual([r["priority_order"] for r in report["rows"]],
                         sorted(r["priority_order"] for r in report["rows"]))
        self.assertTrue(all(r["same_physical_event_verified"] is False and
                            r["independent_nonfire_verified"] is False and
                            r["risk_or_forecast_score"] is None for r in report["rows"]))
        self.assertEqual(report["verified_same_event_crosswalks"], 0)
        self.assertEqual(report["verified_nonfire_labels"], 0)
        self.assertFalse(report["measured_model_skill"])
        self.assertTrue(report["candidate_linked_pages_not_a_complete_calfire_fire_census"])
        self.assertEqual(report, queue(self.casebook, lineage_audit(self.casebook)))

    def test_two_unresolved_reviewers_have_no_identity_and_appropriate_next_steps(self):
        report = queue(self.casebook,
                       lineage_audit(self.casebook, self.filled("alice"), self.filled("bob")))
        reviewed = [r for r in report["rows"] if r["original_lead_count"] > 1]
        self.assertTrue(reviewed)
        self.assertTrue(all(r["review_status"] == "both_unresolved" for r in reviewed))
        self.assertTrue(all(r["review_hypothesis"] is None for r in reviewed))
        self.assertTrue(all(r["unresolved_evidence_gates"] for r in reviewed))
        for r in report["rows"]:
            if r["original_lead_count"] == 1:
                self.assertEqual(r["priority_group"],
                                 "shared_original_source" if r["shared_source_page"]
                                 else "single_name_lead")
            if r["original_lead_count"] == 0:
                self.assertEqual(r["priority_group"], "no_name_lead")
                self.assertIsNone(r["review_hypothesis"])

    def test_source_lineage_mismatch_and_false_truth_fail_closed(self):
        safe = lineage_audit(self.casebook)
        with self.assertRaisesRegex(ValueError, "bound to original"):
            queue(self.casebook, dict(safe, original_casebook_sha256="0"*64))
        with self.assertRaisesRegex(ValueError, "bound to original"):
            queue(self.casebook, dict(safe, verified_nonfire_labels=1))
        missing = copy.deepcopy(safe)
        missing["cases"].pop()
        with self.assertRaisesRegex(ValueError, "duplicate or missing"):
            queue(self.casebook, missing)
        bad = copy.deepcopy(self.casebook)
        bad["cases"][0]["event_identity_verified"] = True
        with self.assertRaises(ValueError):
            queue(bad, safe)

    def test_csv_and_html_export_security_and_original_evidence_integrity(self):
        report = queue(self.casebook, lineage_audit(self.casebook))
        csv = csv_queue(report)
        self.assertIn("candidate_id,manual_priority_group", csv)
        self.assertEqual(csv.count("\r\n"), len(report["rows"]) + 1)
        markup = offline_html(report)
        self.assertIn("Content-Security-Policy", markup)
        self.assertIn("connect-src &#x27;none&#x27;", markup)
        self.assertIn("form-action &#x27;none&#x27;", markup)
        self.assertIn('id="case-list"', markup)
        self.assertIn('id="session-file"', markup)
        self.assertIn("WildfireResearch.mount", markup)
        self.assertNotIn('<script src="https:', markup)
        self.assertNotIn('fetch(', markup)
        script = re.search(r"<script>(.*?)</script>", markup, re.DOTALL).group(1)
        csp = re.search(r"script-src &#x27;sha256-([^&#]+)&#x27;", markup).group(1)
        self.assertEqual(__import__("base64").b64encode(
            hashlib.sha256(script.encode()).digest()).decode(), csp)
        fake = dict(report, verified_same_event_crosswalks=1)
        with self.assertRaisesRegex(ValueError, "forged"):
            offline_html(fake)
        fake = copy.deepcopy(report)
        fake["rows"][0]["mtbs"]["name"] = '=HYPERLINK("https://evil.example", "bad")'
        self.assertIn("'=HYPERLINK", csv_queue(fake))
        # The page carries base64-encoded UTF-8 JSON, never raw remote HTML.
        fake["rows"][0]["mtbs"]["name"] = '<img src=x onerror=alert(1)>'
        self.assertNotIn("<img src=x", offline_html(fake))

    def test_cli_generates_private_queue_and_refuses_reuse_or_source_tampering(self):
        output = self.root / "private-workbench"
        cmd = [sys.executable, "-m", "fire_public.research_workbench",
               "--study-dir", str(self.study),
               "--calfire-archive-dir", str(self.annual),
               "--output-dir", str(output)]
        for folder in self.batches:
            cmd.extend(["--batch", str(folder)])
        p = subprocess.run(cmd, text=True, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)["verified_event_labels"], 0)
        self.assertTrue((output / "index.html").is_file())
        self.assertEqual(json.loads((output / "queue.json").read_text())["verified_nonfire_labels"], 0)
        self.assertEqual((output / "queue.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((output / "index.html").stat().st_mode & 0o777, 0o600)
        self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        data = next(self.study.glob("nifc-*-page-*.geojson"))
        data.write_bytes(data.read_bytes() + b" ")
        cmd[cmd.index("--output-dir") + 1] = str(self.root / "tampered")
        self.assertNotEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.assertFalse((self.root / "tampered").exists())

    def test_private_output_cannot_be_committed_to_public_repository(self):
        target = Path(__file__).resolve().parents[1] / "private-research-export"
        cmd = [sys.executable, "-m", "fire_public.research_workbench",
               "--study-dir", str(self.study),
               "--calfire-archive-dir", str(self.annual),
               "--output-dir", str(target)]
        for folder in self.batches:
            cmd.extend(["--batch", str(folder)])
        p = subprocess.run(cmd, text=True, capture_output=True)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("public Git repository", p.stderr)
        self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
