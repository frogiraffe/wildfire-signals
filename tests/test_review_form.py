"""Offline form and exact existing vote schema; no external wildfire data in tests."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.review_form import render_form, STYLE, SCRIPT
from fire_public.review_intake import _votes


class OfflineReviewFormTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.queue = self.root / "queue.json"
        self.payload = {
            "schema_version": 1,
            "state": "unadjudicated_review_queue",
            "cases": [
                {"case_id": "official:2018:1",
                 "kind": "retrospective_official_perimeter_review",
                 "source_fire_year": 2018, "source_object_id": 1,
                 "source_name": "</script><script>alert('BAD')</script>",
                 "proposed_label": None},
                {"case_id": "frame:control-1",
                 "kind": "independent_frame_review", "region_id": "CA-1",
                 "latitude": 36.9, "longitude": 30.7,
                 "decision_at": "2018-09-01T12:00:00Z",
                 "proposed_label": None}
            ]
        }
        self.queue.write_text(json.dumps(self.payload),encoding="utf-8")

    def test_self_contained_csp_and_encoded_untrusted_provider_names(self):
        html = render_form(self.queue,"Reviewer α")
        self.assertIn('Content-Security-Policy', html)
        self.assertIn("connect-src &#x27;none&#x27;", html)
        self.assertIn("default-src &#x27;none&#x27;",html)
        self.assertIn("script-src &#x27;sha256-",html)
        self.assertIn("style-src &#x27;sha256-",html)
        self.assertNotIn("</script><script>alert",html)
        self.assertIn("Uint8Array.from",html)
        self.assertIn("new TextDecoder('utf-8')",html)
        self.assertIn("No decision is prefilled",html)
        self.assertNotIn("reviewer-b",html)
        self.assertIn("Reviewer: <strong id=",html)
        self.assertNotIn("fetch(",html)
        self.assertNotIn("localStorage",html)
        self.assertNotIn("sessionStorage",html)

    def test_cli_creates_html_and_refuses_existing_source_or_output(self):
        target=self.root/"review.html"
        cmd=[sys.executable,"-m","fire_public.review_form","--queue",str(self.queue),
             "--reviewer-id","independent-a","--html",str(target)]
        done=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        msg=json.loads(done.stdout)
        self.assertEqual(msg["source_queue_sha256"],
                         hashlib.sha256(self.queue.read_bytes()).hexdigest())
        self.assertIn("Validate and download private votes JSON",target.read_text())
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        bad=cmd[:]
        bad[-1]=str(self.queue)
        self.assertNotEqual(subprocess.run(bad,capture_output=True).returncode,0)
        self.assertEqual(len(json.loads(self.queue.read_text())["cases"]),2)

    def test_verified_official_context_annotates_only_source_lead(self):
        import base64
        rechecked={
            "queue_sha256":hashlib.sha256(self.queue.read_bytes()).hexdigest(),
            "official_source_context_consistent":True,
            "valid_binary_outcomes_created":0,
            "case_findings":[{
                "case_id":"official:2018:1",
                "source_record_status":"same_content_as_archived",
                "fresh_feature_sha256":"a"*64,
                "context_captured_at":"2026-10-13T12:00:00+00:00",
                "independent_outcome_verified":False,
            }],
        }
        output=render_form(self.queue,"reviewer-a",official_context_audit=rechecked)
        payload=output.split("const packed = '",1)[1].split("';",1)[0]
        data=json.loads(base64.b64decode(payload).decode())
        self.assertEqual(len(data["cases"]),2)
        self.assertEqual(data["cases"][0]["official_context"]["fresh_feature_sha256"],"a"*64)
        self.assertIsNone(data["cases"][1]["official_context"])
        self.assertIn("independent occurrence/nonfire outcome NOT verified",output)
        rejected=dict(rechecked,queue_sha256="0"*64)
        with self.assertRaisesRegex(ValueError,"exact review queue"):
            render_form(self.queue,"reviewer-a",official_context_audit=rejected)
        rejected=dict(rechecked,valid_binary_outcomes_created=1)
        with self.assertRaisesRegex(ValueError,"exact review queue"):
            render_form(self.queue,"reviewer-a",official_context_audit=rejected)

    def test_existing_review_intake_accepts_identical_vote_schema(self):
        digest=hashlib.sha256(self.queue.read_bytes()).hexdigest()
        votes={
            "schema_version":1,"queue_sha256":digest,
            "reviewer_id":"reviewer-a",
            "votes":[
                {"case_id":"official:2018:1","status":"vote",
                 "reviewer_label":1,"independent_evidence_checked":True,
                 "evidence_url":"https://example.org/independent/fire",
                 "reviewed_at":"2026-10-13T12:00:00Z"},
                {"case_id":"frame:control-1","status":"abstain",
                 "reason":"Independent records not yet available"}
            ],
        }
        path=self.root/"vote.json"
        path.write_text(json.dumps(votes))
        reviewer,by_id=_votes(path,set(c["case_id"] for c in self.payload["cases"]),digest)
        self.assertEqual(reviewer,"reviewer-a")
        self.assertEqual(by_id["official:2018:1"]["reviewer_label"],1)
        self.assertEqual(by_id["frame:control-1"]["status"],"abstain")


if __name__=="__main__":
    unittest.main()
