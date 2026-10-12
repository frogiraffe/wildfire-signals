"""Double blind pair review reconciliation. All identities and sources synthetic.

No test review is proof of a real wildfire event, negative or independent
record availability. Real source packet generation is independently tested CI.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

from fire_public.mtbs_match_review import load_study
from fire_public.mtbs_pair_reconcile import reconcile, render_html
from test_mtbs_match_review import PairReviewTests


class PairReconciliationTests(unittest.TestCase):
    def setUp(self):
        f=PairReviewTests("test_valid_manual_vote_produces_only_hypothesis_statistics")
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.fixture=f
        self.root=f.root
        self.study=f.study
        _,self.digest,self.cases=load_study(self.study)
        self.assertGreaterEqual(len(self.cases),5)
        self.first=self.root/"researcher-a-private.json"
        self.second=self.root/"researcher-b-private.json"
        self.first_obj=self._vote("researcher-a")
        self.second_obj=self._vote("researcher-b")
        self._save()

    def _vote(self,reviewer):
        return {
            "schema_version":1,"source_bundle_sha256":self.digest,
            "reviewer_id":reviewer,"reviewed_at":"2026-10-13T15:00:00Z",
            "classifications_are_unverified_hypotheses":True,
            "votes":[{
                "candidate_id":case["candidate_id"],
                "decision":"inconclusive",
                "reason":"The agency source names need further corroboration.",
                "evidence_url":None,
            } for case in self.cases],
        }

    def _hypothesis(self,obj,index,decision,url="https://example.org/incident/test"):
        obj["votes"][index]={
            "candidate_id":self.cases[index]["candidate_id"],
            "decision":decision,
            "reason":"Original agency event records provide a provisional working hypothesis.",
            "evidence_url":url,
        }

    def _save(self):
        self.first.write_text(json.dumps(self.first_obj),encoding="utf-8")
        self.second.write_text(json.dumps(self.second_obj),encoding="utf-8")

    def _fill(self):
        self._hypothesis(self.first_obj,0,"same_event_hypothesis")
        self._hypothesis(self.second_obj,0,"same_event_hypothesis")
        self._hypothesis(self.first_obj,1,"different_event_hypothesis",
                         "https://example.org/source/a")
        self._hypothesis(self.second_obj,1,"different_event_hypothesis",
                         "https://example.org/source/b")
        self._hypothesis(self.first_obj,2,"same_event_hypothesis")
        self._hypothesis(self.second_obj,2,"different_event_hypothesis")
        self._hypothesis(self.first_obj,3,"same_event_hypothesis")
        self._save()

    def test_all_dispositions_correct_and_never_ground_truth(self):
        self._fill()
        result=reconcile(self.study,self.first,self.second)
        self.assertEqual(result["candidates_checked"],len(self.cases))
        self.assertEqual(result["dispositions"]["concordant_unverified_hypothesis"],2)
        self.assertEqual(result["dispositions"]["conflicting_hypotheses"],1)
        self.assertEqual(result["dispositions"]["partially_inconclusive"],1)
        self.assertEqual(result["dispositions"]["both_inconclusive"],len(self.cases)-4)
        self.assertEqual(result["same_fire_events_independently_verified"],0)
        self.assertEqual(result["independently_verified_nonfire_cases"],0)
        self.assertEqual(result["binary_prediction_labels_created"],0)
        self.assertFalse(result["model_skill_measured"])
        rows={r["candidate_id"]:r for r in result["candidates"]}
        shared=rows[self.cases[0]["candidate_id"]]
        self.assertEqual(shared["cited_evidence_relation"],
                         "same_cited_url_not_independent_sources")
        self.assertIn("reviewers_cited_same_url_no_source_independence",
                      shared["human_follow_up_flags"])
        distinct=rows[self.cases[1]["candidate_id"]]
        self.assertEqual(distinct["cited_evidence_relation"],
                         "different_cited_urls_not_source_independence")
        self.assertIsNone(rows[self.cases[2]["candidate_id"]]["agreed_hypothesis"])
        self.assertIsNone(rows[self.cases[3]["candidate_id"]]["agreed_hypothesis"])
        self.assertEqual(result["source_study_sha256"],
                         hashlib.sha256((self.study/"aligned-study.json").read_bytes()).hexdigest())
        self.assertEqual([r["role"] for r in result["reviewers"]],
                         ["first_blind_review","second_blind_review"])
        self.assertEqual(result["reviewers"][0]["vote_sha256"],
                         hashlib.sha256(self.first.read_bytes()).hexdigest())

    def test_reviewed_untouched_inconclusive_is_unresolved_not_a_negative(self):
        result=reconcile(self.study,self.first,self.second)
        self.assertEqual(result["dispositions"]["both_inconclusive"],len(self.cases))
        self.assertTrue(all(r["fire_absence_verified"] is False
                            for r in result["candidates"]))

    def test_same_reviewer_identity_casefold_rejected(self):
        self.second_obj["reviewer_id"]="RESEARCHER-A"
        self._save()
        with self.assertRaisesRegex(ValueError,"distinct reviewer identities"):
            reconcile(self.study,self.first,self.second)

    def test_uses_distinct_physical_vote_files(self):
        with self.assertRaisesRegex(ValueError,"different vote file"):
            reconcile(self.study,self.first,self.first)
        inside=self.study/"private-votes.json"
        inside.write_text(self.first.read_text())
        with self.assertRaisesRegex(ValueError,"cannot be stored in public"):
            reconcile(self.study,inside,self.second)

    def test_missing_duplicate_or_other_study_votes_fail_closed(self):
        self.second_obj["votes"].pop()
        self._save()
        with self.assertRaisesRegex(ValueError,"every proximity candidate"):
            reconcile(self.study,self.first,self.second)
        self.second_obj=self._vote("researcher-b")
        self.second_obj["votes"][0]["candidate_id"]=self.cases[1]["candidate_id"]
        self._save()
        with self.assertRaisesRegex(ValueError,"duplicate, missing"):
            reconcile(self.study,self.first,self.second)
        self.second_obj=self._vote("researcher-b")
        self.second_obj["source_bundle_sha256"]="0"*64
        self._save()
        with self.assertRaisesRegex(ValueError,"exact source"):
            reconcile(self.study,self.first,self.second)

    def test_retrospectively_impossible_review_time_rejected(self):
        self.second_obj["reviewed_at"]="2017-01-01T00:00:00Z"
        self._save()
        with self.assertRaisesRegex(ValueError,"predates original source"):
            reconcile(self.study,self.first,self.second)

    def test_output_html_escapes_untrusted_reviewer_reason_and_has_no_script(self):
        self._hypothesis(self.first_obj,0,"same_event_hypothesis")
        self._hypothesis(self.second_obj,0,"same_event_hypothesis")
        payload="<img src=x onerror=alert('XSS')> was cited here by agency."
        self.second_obj["votes"][0]["reason"]=payload
        self._save()
        html=render_html(reconcile(self.study,self.first,self.second))
        self.assertIn("&lt;img src=x onerror=alert(",html)
        self.assertNotIn("<img src=x",html)
        self.assertIn("Content-Security-Policy",html)
        self.assertIn("script-src &#x27;none&#x27;",html)
        self.assertNotIn("<script",html)
        self.assertIn("Cited source</a>",html)
        self.assertIn("human hypotheses",html)
        self.assertNotIn("verified same-fire",html.lower())

    def test_original_record_mutation_or_response_hash_blocks_reconcile(self):
        self._fill()
        source=next(self.study.glob("nifc-*-page-*.geojson"))
        source.write_bytes(source.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            reconcile(self.study,self.first,self.second)

    def test_cli_writes_both_private_files_exclusive_and_links_back_to_sources(self):
        self._fill()
        output_json=self.root/"coordinator-reconciliation.json"
        output_html=self.root/"coordinator-reconciliation.html"
        cmd=[sys.executable,"-m","fire_public.mtbs_pair_reconcile",
             "--study-dir",str(self.study),"--first",str(self.first),
             "--second",str(self.second),"--json",str(output_json),
             "--html",str(output_html)]
        done=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        public=json.loads(output_json.read_text())
        self.assertEqual(public["same_fire_events_independently_verified"],0)
        self.assertEqual(public["dispositions"]["conflicting_hypotheses"],1)
        self.assertIn(self.cases[0]["candidate_id"],output_html.read_text())
        self.assertEqual(json.loads(done.stdout)["confirmed_event_identities"],0)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        swapped=cmd[:]
        swapped[-1]=str(self.first)
        self.assertNotEqual(subprocess.run(swapped,capture_output=True).returncode,0)
        self.assertEqual(json.loads(self.first.read_text())["reviewer_id"],"researcher-a")


if __name__=="__main__":
    unittest.main()
