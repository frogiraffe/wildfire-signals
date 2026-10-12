"""Original provider fixtures and *synthetic* independently authored documents.

No evidence in this test suite is genuine third-party corroboration and no
positive/negative wildfire labels, validated same-event crosswalks or model
performance scores are produced.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import unittest

from fire_public.mtbs_event_corroboration import (
    audit, capture, prepare, _source_meta,
)
from test_mtbs_pair_reconcile import PairReconciliationTests

CAPTURED="2026-10-13T13:00:00Z"


class EventCorroborationTests(unittest.TestCase):
    def setUp(self):
        fixture=PairReconciliationTests("test_all_dispositions_correct_and_never_ground_truth")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture=fixture
        self.root=fixture.root
        self.study=fixture.study
        self.store=self.root/"private-third-party"
        self.store.mkdir()
        self.case=fixture.cases[0]
        self.a=self.root/"first-government-report.json"
        self.b=self.root/"second-original-event-report.json"
        self.first_url="https://example.org/research/source-a"
        self.second_url="https://archives.example.net/research/source-b"
        fixture._hypothesis(fixture.first_obj,0,"same_event_hypothesis",self.first_url)
        fixture._hypothesis(fixture.second_obj,0,"same_event_hypothesis",self.second_url)
        fixture._save()

    def metadata(self,who):
        provider, url,group=(
            ("original-organization-a",self.first_url,"independent-agency-records")
            if who=="a" else
            ("original-organization-b",self.second_url,"independent-historical-archive"))
        return {
            "schema_version":1,
            "candidate_id":self.case["candidate_id"],
            "mtbs_fire_id":self.case["mtbs"]["fire_id"],
            "nifc_object_id":self.case["nifc"]["object_id"],
            "nifc_source_identity":self.case["nifc"]["source_identity"],
            "source_url":url,"rights_url":"https://example.org/license",
            "publisher_id":provider,"upstream_family":group,
            "source_record_id":"fixture-"+who,
            "source_kind":"original archived agency incident record",
            "upstream_role":"firsthand_original_record",
            "relation_claim":"same_event_document_claim",
            "source_published_at":"2026-10-13T10:00:00Z",
            "source_event_at":"2018-07-20T00:00:00Z",
            "researcher_note":"Synthetic source under review; publisher identity not authenticated.",
        }

    def one(self,who,**changes):
        path=self.root/("document-"+who+".bin")
        meta=self.root/("source-"+who+".json")
        path.write_bytes(b"SYNTHETIC EVIDENCE ONLY " + who.encode())
        values=self.metadata(who)
        values.update(changes)
        meta.write_text(json.dumps(values))
        return capture(self.study,self.store,meta,path,captured_at=CAPTURED)

    def both(self):
        return self.one("a"),self.one("b")

    def test_source_backed_blank_real_candidate_casebook_has_no_fabricated_evidence(self):
        result=prepare(self.study)
        self.assertEqual(result["candidate_count"],len(self.fixture.cases))
        self.assertEqual(result["verified_event_identities"],0)
        self.assertEqual(result["verified_nonfire_labels"],0)
        self.assertTrue(all(c["documentary_sources_collected"]==0
                            for c in result["cases"]))
        self.assertEqual(result["cases"][0]["mtbs_fire_id"],self.case["mtbs"]["fire_id"])
        self.assertEqual(result["cases"][0]["nifc_source_identity"],
                         self.case["nifc"]["source_identity"])

    def test_original_bytes_and_two_distinct_claimed_lineages_are_review_ready_not_truth(self):
        a,b=self.both()
        result=audit(self.study,self.store,self.fixture.first,self.fixture.second)
        target=next(r for r in result["cases"] if r["candidate_id"]==self.case["candidate_id"])
        self.assertEqual(target["research_status"],
             "documentary_case_ready_for_external_adjudication_not_verified")
        self.assertEqual(target["unresolved_gates"],[])
        self.assertEqual(target["document_count"],2)
        self.assertFalse(target["event_identity_verified"])
        self.assertFalse(target["independent_nonfire_verified"])
        self.assertEqual(result["private_source_receipts_checked"],2)
        self.assertEqual(result["statuses"][
            "documentary_case_ready_for_external_adjudication_not_verified"],1)
        self.assertEqual(result["statuses"]["further_independent_evidence_required"],
                         len(self.fixture.cases)-1)
        self.assertEqual(result["verified_event_crosswalks"],0)
        self.assertEqual(result["independent_nonfire_labels"],0)
        self.assertEqual(len(list((self.store/"event-corroboration/blobs").iterdir())),2)
        self.assertEqual(len(list((self.store/"event-corroboration/receipts").iterdir())),2)
        self.assertEqual(self.one("a")["receipt_id"],a["receipt_id"])
        self.assertEqual(self.one("b")["receipt_id"],b["receipt_id"])

    def test_unreviewed_sources_do_not_create_verified_event(self):
        self.both()
        status=audit(self.study,self.store)
        first=next(x for x in status["cases"] if x["candidate_id"]==self.case["candidate_id"])
        self.assertIn("independent_human_pair_reviews_not_provided",first["unresolved_gates"])
        self.assertEqual(status["verified_event_crosswalks"],0)

    def test_missing_or_same_document_linked_to_two_human_votes_fails_readiness(self):
        self.one("a")
        result=audit(self.study,self.store,self.fixture.first,self.fixture.second)
        first=next(x for x in result["cases"] if x["candidate_id"]==self.case["candidate_id"])
        self.assertIn("human_review_evidence_urls_not_both_archived",first["unresolved_gates"])
        self.fixture.second_obj["votes"][0]["evidence_url"]=self.first_url
        self.fixture._save()
        result=audit(self.study,self.store,self.fixture.first,self.fixture.second)
        first=next(x for x in result["cases"] if x["candidate_id"]==self.case["candidate_id"])
        self.assertIn("same_document_cited_by_both_reviewers",first["unresolved_gates"])

    def test_different_claims_and_missing_source_dates_block_readiness(self):
        self.one("a")
        self.one("b",relation_claim="different_event_document_claim",
                 source_event_at=None)
        out=audit(self.study,self.store,self.fixture.first,self.fixture.second)
        row=next(x for x in out["cases"] if x["candidate_id"]==self.case["candidate_id"])
        self.assertIn("source_document_relation_claims_disagree",row["unresolved_gates"])
        self.assertIn("source_event_time_evidence_missing",row["unresolved_gates"])

    def test_two_citations_from_same_declared_upstream_family_are_insufficient(self):
        self.one("a")
        self.one("b",upstream_family="independent-agency-records")
        out=audit(self.study,self.store,self.fixture.first,self.fixture.second)
        row=next(x for x in out["cases"] if x["candidate_id"]==self.case["candidate_id"])
        self.assertIn("two_distinct_declared_publisher_and_upstream_families_required",
                      row["unresolved_gates"])

    def test_cited_document_captured_after_reviewer_decision_is_flagged(self):
        self.one("a")
        # The second file is archived after the reviewer record date 15:00.
        doc=self.root/"late-document.bin";doc.write_bytes(b"Late evidence")
        meta=self.root/"late-source.json";meta.write_text(json.dumps(self.metadata("b")))
        capture(self.study,self.store,meta,doc,captured_at="2026-10-13T16:30:00Z")
        result=audit(self.study,self.store,self.fixture.first,self.fixture.second)
        target=next(x for x in result["cases"] if x["candidate_id"]==self.case["candidate_id"])
        self.assertIn("review_citation_document_archived_after_review",
                      target["unresolved_gates"])

    def test_source_date_disagreements_cannot_be_hidden(self):
        self.one("a")
        self.one("b",source_event_at="2018-07-21T00:00:00Z")
        result=audit(self.study,self.store,self.fixture.first,self.fixture.second)
        target=next(x for x in result["cases"] if x["candidate_id"]==self.case["candidate_id"])
        self.assertIn("third_party_source_event_dates_disagree",target["unresolved_gates"])

    def test_fake_source_case_identity_never_enter_archive(self):
        meta=self.metadata("a")
        meta["nifc_source_identity"]="fake-foreign-object"
        file=self.root/"wrong.json";file.write_text(json.dumps(meta))
        doc=self.root/"wrong.bin";doc.write_bytes(b"Source bytes")
        with self.assertRaisesRegex(ValueError,"do not match original candidate"):
            capture(self.study,self.store,file,doc,captured_at=CAPTURED)
        self.assertFalse((self.store/"event-corroboration").exists())

    def test_corrupted_original_document_or_receipt_rejected(self):
        receipt=self.one("a")
        blob=self.store/"event-corroboration/blobs"/(receipt["document_sha256"]+".bin")
        blob.write_bytes(b"TAMPERED")
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            audit(self.study,self.store)
        blob.write_bytes(b"SYNTHETIC EVIDENCE ONLY a")
        r=self.store/"event-corroboration/receipts"/(receipt["receipt_id"]+".json")
        r.write_bytes(r.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"content integrity mismatch"):
            audit(self.study,self.store)

    def test_review_vote_missing_or_same_reviewer_does_not_admit(self):
        self.both()
        self.fixture.second_obj["reviewer_id"]="RESEARCHER-A"
        self.fixture._save()
        with self.assertRaisesRegex(ValueError,"distinct reviewer identities"):
            audit(self.study,self.store,self.fixture.first,self.fixture.second)
        with self.assertRaisesRegex(ValueError,"two separate human reviewer"):
            audit(self.study,self.store,self.fixture.first,None)

    def test_original_government_source_corruption_prohibits_dossier_creation(self):
        data=next(self.study.glob("nifc-*-page-*.geojson"))
        data.write_bytes(data.read_bytes()+b"\n")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            prepare(self.study)
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            audit(self.study,self.store)

    def test_cli_prepare_capture_and_audit_never_overwrite_original(self):
        prep=self.root/"private-blank-casebook.json"
        cmd=[sys.executable,"-m","fire_public.mtbs_event_corroboration","prepare",
             "--study-dir",str(self.study),"--output",str(prep)]
        proc=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(prep.read_text())["candidate_count"],
                         len(self.fixture.cases))
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        self.both()
        audit_dest=self.root/"private-audit.json"
        cmd=[sys.executable,"-m","fire_public.mtbs_event_corroboration","audit",
             "--study-dir",str(self.study),"--store",str(self.store),
             "--first",str(self.fixture.first),"--second",str(self.fixture.second),
             "--output",str(audit_dest)]
        proc=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        result=json.loads(audit_dest.read_text())
        self.assertEqual(result["verified_event_crosswalks"],0)
        self.assertEqual(result["private_source_receipts_checked"],2)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)


if __name__ == "__main__":
    unittest.main()
