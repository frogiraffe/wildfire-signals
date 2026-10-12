"""Audit real original provider shapes through offline pair-review packet and votes.

The ArcGIS data here are synthetic fixtures; the existing shared-region
live-GitHub-Action job separately tests genuine US government APIs.
"""
from __future__ import annotations

import base64
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.mtbs_match_review import (
    load_study, render_packet, validate_votes,
)
from fire_public.mtbs_region_study import write_capture
from test_mtbs_region_study import SharedRegionStudyTests


class PairReviewTests(unittest.TestCase):
    def setUp(self):
        fixture=SharedRegionStudyTests("test_queries_use_identical_region_and_year_before_selection")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture=fixture
        self.root=fixture.root
        self.study=self.root/"aligned-source"
        self.report,self.raw=fixture.study()
        write_capture(self.study,self.report,self.raw)

    def sample_votes(self):
        _,digest,cases=load_study(self.study)
        return {
            "schema_version":1,
            "source_bundle_sha256":digest,
            "reviewer_id":"researcher-fixture-a",
            "reviewed_at":"2026-10-13T15:00:00Z",
            "classifications_are_unverified_hypotheses":True,
            "votes":[{
                "candidate_id":c["candidate_id"],
                "decision":"same_event_hypothesis" if i==0 else "inconclusive",
                "reason":"Possible agreement in historical map but not scientifically validated",
                "evidence_url":"https://example.org/historical/source" if i==0 else None,
            } for i,c in enumerate(cases)]
        }

    def test_source_verified_packet_and_original_identity(self):
        report,digest,cases=load_study(self.study)
        self.assertGreater(len(cases),0)
        self.assertEqual(digest,hashlib.sha256((self.study/"aligned-study.json").read_bytes()).hexdigest())
        self.assertTrue(all(row["hypothesis_not_ground_truth"] for row in cases))
        self.assertTrue(all(row["preview_is_simplified_not_gis_validated"] for row in cases))
        self.assertEqual(cases[0]["mtbs"]["fire_type"],"Wildfire")
        page=render_packet(self.study,"researcher-fixture-a")
        self.assertIn("Content-Security-Policy",page)
        self.assertIn("connect-src &#x27;none&#x27;",page)
        self.assertIn("Source SHA-256",page)
        self.assertNotIn("fetch(",page)
        self.assertNotIn("localStorage",page)
        self.assertNotIn("<img src=",page)
        encoded=page.split("atob('",1)[1].split("')",1)[0]
        data=json.loads(base64.b64decode(encoded))
        self.assertEqual(len(data["cases"]),len(cases))
        self.assertEqual(data["source_bundle_sha256"],digest)
        self.assertEqual(data["cases"][0]["candidate_id"],cases[0]["candidate_id"])

    def test_valid_manual_vote_produces_only_hypothesis_statistics(self):
        votes=self.sample_votes()
        path=self.root/"votes.json"
        path.write_text(json.dumps(votes),encoding="utf-8")
        output=validate_votes(self.study,path)
        self.assertEqual(output["candidates_reviewed"],len(votes["votes"]))
        self.assertEqual(output["dispositions"]["same_event_hypothesis"],1)
        self.assertEqual(output["same_event_verified"],0)
        self.assertEqual(output["negative_labels_created"],0)
        self.assertEqual(output["scientific_status"],
            "manual_hypotheses_not_independent_outcome_validation")

    def test_tampered_raw_nifc_geometry_rejected(self):
        file=next(self.study.glob("nifc-*-page-*.geojson"))
        file.write_text(file.read_text()+" ")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            load_study(self.study)

    def test_tampered_mtbs_original_source_rejected(self):
        file=self.study/"mtbs-2018-roi-points.json"
        file.write_text(file.read_text().replace("TEST_FIRE_100","FAKE_FIRE_100"))
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            load_study(self.study)

    def test_source_population_denominators_recomputed_from_provider_id_bytes(self):
        file=self.study/"aligned-study.json"
        obj=json.loads(file.read_text())
        obj["source_population"]["mtbs_roi_object_ids"]+=1
        file.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError,"declared source ROI population"):
            load_study(self.study)

    def test_https_proof_needs_actual_source_hostname(self):
        vote=self.sample_votes()
        vote["votes"][0]["evidence_url"]="https://"
        file=self.root/"bad-evidence.json"
        file.write_text(json.dumps(vote))
        with self.assertRaisesRegex(ValueError,"source URL required"):
            validate_votes(self.study,file)

    def test_modified_candidate_provenance_rejected(self):
        file=self.study/"aligned-study.json"
        report=json.loads(file.read_text())
        report["candidate_pairs"][0]["same_event_verified"]=True
        file.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError,"falsely claims independent event identity"):
            load_study(self.study)
        report=json.loads(file.read_text())
        report["candidate_pairs"][0]["same_event_verified"]=False
        report["candidate_pairs"].pop()
        file.write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError,"missing proximity pair"):
            load_study(self.study)

    def test_modified_nifc_geometry_or_mtbs_fire_type_cannot_skip_source_check(self):
        file=self.study/"aligned-study.json"
        old=file.read_text()
        doc=json.loads(old)
        doc["nifc_polygons"][0]["name"]="FAKE govt event"
        file.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,"NIFC selected source properties"):
            load_study(self.study)
        doc=json.loads(old)
        doc["mtbs_points"][0]["source_fire_type"]="Prescribed Burn"
        file.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,"MTBS source record tampered"):
            load_study(self.study)

    def test_missing_evidence_for_hypothesis_and_unreviewed_rejected(self):
        vote=self.sample_votes()
        path=self.root/"votes.json"
        vote["votes"][0]["evidence_url"]=None
        path.write_text(json.dumps(vote))
        with self.assertRaisesRegex(ValueError,"source URL required"):
            validate_votes(self.study,path)
        vote["votes"][0]["decision"]="unreviewed"
        path.write_text(json.dumps(vote))
        with self.assertRaisesRegex(ValueError,"review disposition must be explicit"):
            validate_votes(self.study,path)

    def test_review_missing_or_duplicate_pairs_denied(self):
        vote=self.sample_votes()
        path=self.root/"votes.json"
        vote["votes"].pop()
        path.write_text(json.dumps(vote))
        with self.assertRaisesRegex(ValueError,"every proximity candidate"):
            validate_votes(self.study,path)
        vote=self.sample_votes()
        vote["votes"][1]["candidate_id"]=vote["votes"][0]["candidate_id"]
        path.write_text(json.dumps(vote))
        with self.assertRaisesRegex(ValueError,"duplicate, missing"):
            validate_votes(self.study,path)

    def test_reject_change_in_original_source_bundle_hash(self):
        vote=self.sample_votes()
        path=self.root/"votes.json"
        vote["source_bundle_sha256"]="0"*64
        path.write_text(json.dumps(vote))
        with self.assertRaisesRegex(ValueError,"does not refer to exact source"):
            validate_votes(self.study,path)
        vote["source_bundle_sha256"]=self.sample_votes()["source_bundle_sha256"]
        vote["classifications_are_unverified_hypotheses"]=False
        path.write_text(json.dumps(vote))
        with self.assertRaisesRegex(ValueError,"scientific restrictions"):
            validate_votes(self.study,path)

    def test_command_line_packet_and_validator(self):
        packet=self.root/"pair-packet.html"
        cli=[sys.executable,"-m","fire_public.mtbs_match_review",
             "packet","--study-dir",str(self.study),
             "--reviewer-id","researcher-a","--html",str(packet)]
        done=subprocess.run(cli,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertIn("Relative geometry preview",packet.read_text())
        self.assertNotEqual(subprocess.run(cli,capture_output=True).returncode,0)
        vote_file=self.root/"review.json"
        vote_file.write_text(json.dumps(self.sample_votes()))
        out=self.root/"review-audit.json"
        cli=[sys.executable,"-m","fire_public.mtbs_match_review","validate",
             "--study-dir",str(self.study),
             "--votes",str(vote_file),"--output",str(out)]
        done=subprocess.run(cli,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual(json.loads(out.read_text())["same_event_verified"],0)
        self.assertNotEqual(subprocess.run(cli,capture_output=True).returncode,0)


if __name__=="__main__":
    unittest.main()
