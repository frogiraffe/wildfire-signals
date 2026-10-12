"""Independent reviewer intake and conflict preservation through the real exporter."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.review_intake import packet, reconcile, details_template
from fire_public.label_review import finalize_queue
from test_label_review import PROTOCOL, review


class ReviewIntakeTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root=Path(tmp.name)
        self.queue=root/"queue.json"
        self.protocol=root/"protocol.json"
        self.details=root/"details.json"
        self.first=root/"first.json"
        self.second=root/"second.json"
        self.reviews=root/"reviews.json"
        self.queue_data={"schema_version":1,"state":"unadjudicated_review_queue",
                         "as_of":"2026-10-13T00:00:00+00:00",
                         "official_source":"https://example.org/nifc",
                         "sampling_frame":{"source":"https://example.org/frame",
                                           "input_sha256":"a"*64},
                         "cases":[
                             {"case_id":"official:2017:17","kind":"retrospective_official_perimeter_review",
                              "source_fire_year":2017,"source_object_id":17,
                              "source_name":"<script>alert(1)</script>","proposed_label":None},
                             {"case_id":"frame:control-2017","kind":"independent_frame_review",
                              "sampling_unit_id":"control-2017","region_id":"region-2017",
                              "latitude":37.0,"longitude":-120.0,
                              "decision_at":"2017-07-05T00:00:00+00:00","proposed_label":None},
                         ]}
        self.queue.write_text(json.dumps(self.queue_data),encoding="utf-8")
        self.protocol.write_text(json.dumps(PROTOCOL),encoding="utf-8")
        self.decisions=[review(c,i) for i,c in enumerate(self.queue_data["cases"])]
        self.details.write_text(json.dumps({"schema_version":1,
            "queue_sha256":self.digest(self.queue),
            "cases":[{k:v for k,v in d.items() if k not in
                ("status","label","primary","secondary","case_id")} | {"case_id":d["case_id"]}
                for d in self.decisions]}),encoding="utf-8")
        self.write_votes()

    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_votes(self, conflict=False):
        for path,who in ((self.first,"reviewer-a"),(self.second,"reviewer-b")):
            votes=[]
            for i,case in enumerate(self.queue_data["cases"]):
                votes.append({"case_id":case["case_id"],"status":"vote",
                    "reviewer_label":int(i==0) if not (conflict and who=="reviewer-b" and i==1) else 1,
                    "independent_evidence_checked":True,
                    "evidence_url":f"https://example.org/{who}/{i}",
                    "reviewed_at":"2026-10-12T13:00:00Z"})
            path.write_text(json.dumps({"schema_version":1,
                "queue_sha256":self.digest(self.queue),"reviewer_id":who,
                "votes":votes}),encoding="utf-8")

    def test_blind_packet_escapes_source_text_and_contains_no_other_votes(self):
        html,template=packet(self.queue,"reviewer-a")
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",html)
        self.assertNotIn("<script>",html)
        self.assertNotIn("reviewer-b",html)
        self.assertEqual(template["queue_sha256"],self.digest(self.queue))
        self.assertTrue(all(v["status"]=="unreviewed" for v in template["votes"]))

    def test_coordinator_template_preserves_frame_identity_without_guessing_labels(self):
        template=details_template(self.queue)
        self.assertEqual(template["queue_sha256"],self.digest(self.queue))
        frame=template["cases"][1]
        self.assertEqual(frame["region_id"],"region-2017")
        self.assertEqual(frame["decision_at"],"2017-07-05T00:00:00+00:00")
        self.assertIsNone(frame["label_source"])
        self.assertNotIn("label",frame)

    def test_independent_votes_reconcile_then_existing_finalize(self):
        reviews,report=reconcile(self.queue,self.first,self.second,self.details,self.protocol)
        self.assertEqual(report["matched"],2)
        self.assertEqual(report["conflicted"],0)
        self.reviews.write_text(json.dumps(reviews),encoding="utf-8")
        rows,manifest,status=finalize_queue(self.queue,self.reviews,self.protocol)
        self.assertEqual([row["label"] for row in rows],[1,0])
        self.assertEqual(status["negative_labels"],1)
        self.assertEqual(manifest["review_decisions_sha256"],self.digest(self.reviews))

    def test_disagreement_stays_unresolved_with_both_votes(self):
        self.write_votes(conflict=True)
        reviews,report=reconcile(self.queue,self.first,self.second,self.details,self.protocol)
        self.assertEqual(report["conflicted"],1)
        entry=reviews["decisions"][1]
        self.assertEqual(entry["status"],"unresolved")
        self.assertEqual({v["reviewer_label"] for v in entry["reviewer_votes"]}, {0,1})
        self.assertEqual(report["conflicted_case_ids"],["frame:control-2017"])

    def test_same_reviewer_or_changed_queue_is_rejected(self):
        second=json.loads(self.second.read_text())
        second["reviewer_id"]="reviewer-a"
        self.second.write_text(json.dumps(second))
        with self.assertRaisesRegex(ValueError,"distinct reviewers"):
            reconcile(self.queue,self.first,self.second,self.details,self.protocol)
        second["reviewer_id"]="reviewer-b"
        second["queue_sha256"]="0"*64
        self.second.write_text(json.dumps(second))
        with self.assertRaisesRegex(ValueError,"queue SHA"):
            reconcile(self.queue,self.first,self.second,self.details,self.protocol)

    def test_vote_cannot_override_top_level_reviewer_identity(self):
        first=json.loads(self.first.read_text())
        first["votes"][0]["reviewer_id"]="reviewer-b"
        self.first.write_text(json.dumps(first))
        with self.assertRaisesRegex(ValueError,"unexpected vote fields"):
            reconcile(self.queue,self.first,self.second,self.details,self.protocol)

    def test_vote_with_missing_evidence_or_incomplete_case_set_is_rejected(self):
        first=json.loads(self.first.read_text())
        first["votes"][0]["independent_evidence_checked"]=False
        self.first.write_text(json.dumps(first))
        with self.assertRaisesRegex(ValueError,"independent evidence"):
            reconcile(self.queue,self.first,self.second,self.details,self.protocol)
        first["votes"][0]["independent_evidence_checked"]=True
        first["votes"].pop()
        self.first.write_text(json.dumps(first))
        with self.assertRaisesRegex(ValueError,"every queued case"):
            reconcile(self.queue,self.first,self.second,self.details,self.protocol)

    def test_cli_packet_and_reconcile_protect_existing_outputs(self):
        brief=self.queue.parent/"reviewer-a.html"
        template=self.queue.parent/"vote-template.json"
        packet_cmd=[sys.executable,"-m","fire_public.review_intake","packet",
            "--queue",str(self.queue),"--reviewer-id","reviewer-a",
            "--html",str(brief),"--vote-template",str(template)]
        result=subprocess.run(packet_cmd,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn("Independent review packet",brief.read_text())
        self.assertNotEqual(subprocess.run(packet_cmd,capture_output=True).returncode,0)
        report=self.queue.parent/"report.json"
        cmd=[sys.executable,"-m","fire_public.review_intake","reconcile",
            "--queue",str(self.queue),"--first",str(self.first),
            "--second",str(self.second),"--details",str(self.details),
            "--protocol",str(self.protocol),"--reviews",str(self.reviews),
            "--report",str(report)]
        result=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(report.read_text())["matched"],2)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)


if __name__=="__main__":
    unittest.main()
