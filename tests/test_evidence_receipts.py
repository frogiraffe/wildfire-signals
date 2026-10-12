"""Test immutable operator source snapshots and strict reviewer evidence binding.

Synthetic source documents are NOT real independent wildfire/non-fire evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.evidence_receipts import capture, audit_receipts
from fire_public.label_review import finalize_queue
from test_label_review import LabelReviewTests


CAPTURED = "2026-10-12T12:00:00Z"
PUBLISHED = "2026-10-12T09:00:00Z"


class EvidenceReceiptTests(unittest.TestCase):
    def setUp(self):
        self.fixture = LabelReviewTests(
            "test_real_sqlite_provenance_to_reviewed_cohort_and_baseline")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.store = self.root / "independent-evidence"
        self.store.mkdir()
        self.fixture.save_reviews()

    def one(self, case, role, *, captured_at=CAPTURED, extra=None):
        entry = next(x for x in self.fixture.decisions if x["case_id"] == case)
        if role == "label":
            url = entry["label_evidence_url"]
            provider_id = entry["label_source_id"]
        elif role in ("primary", "secondary"):
            url = entry[role]["evidence_url"]
            provider_id = entry["label_source_id"]
        else:
            url = entry["negative_coverage"]["completeness_evidence_url"]
            provider_id = entry["label_source_id"]
        meta = {
            "schema_version": 1,
            "case_id": case,
            "role": role,
            "source_url": url,
            "rights_url": "https://example.org/rights",
            "source_kind": ("independent_complete_registry" if role == "coverage"
                            else "independently_reviewed_outcome_record"),
            "source_record_id": provider_id,
            "source_published_at": PUBLISHED,
        }
        if role == "coverage":
            meta.update({
                "coverage_region_id": entry["region_id"],
                "coverage_start_at": entry["negative_coverage"]["start_at"],
                "coverage_end_at": entry["negative_coverage"]["end_at"],
            })
        if extra:
            meta.update(extra)
        marker = case.replace(":", "_")+"-"+role
        snapshot = self.root / (marker+".txt")
        metadata = self.root / (marker+".json")
        snapshot.write_text("SYNTHETIC TEST ONLY independently supplied record " +
                            marker,encoding="utf-8")
        metadata.write_text(json.dumps(meta),encoding="utf-8")
        return capture(snapshot,metadata,self.store,captured_at=captured_at)

    def all(self):
        saved = []
        for entry in self.fixture.decisions:
            for role in ("label","primary","secondary"):
                saved.append(self.one(entry["case_id"],role))
            if entry["label"] == 0:
                saved.append(self.one(entry["case_id"],"coverage"))
        return saved

    def audit(self):
        self.fixture.save_reviews()
        return audit_receipts(self.fixture.queue_file,
                              self.fixture.reviews_file,self.store)

    def strict(self):
        self.fixture.save_reviews()
        return finalize_queue(self.fixture.queue_file,self.fixture.reviews_file,
                              self.fixture.protocol_file,evidence_store=self.store)

    def test_all_receipts_bind_then_export_statistically_structural_cohort(self):
        receipts = self.all()
        self.assertEqual(len(receipts),14)
        report = self.audit()
        self.assertTrue(report["structurally_receipt_complete"])
        self.assertFalse(report["source_authenticity_externally_verified"])
        self.assertFalse(report["independent_fire_negative_truth_verified"])
        self.assertEqual(len(report["review_bindings"]),14)
        rows,manifest,summary=self.strict()
        self.assertEqual(len(rows),4)
        self.assertEqual(manifest["source_receipt_gate"],
                         "hash_checked_operator_captured_snapshots")
        self.assertEqual(len(manifest["source_receipt_bindings"]),14)
        self.assertEqual(summary["source_receipt_bindings"],14)
        self.assertFalse(summary["source_authenticity_externally_verified_by_tool"])
        self.assertEqual(rows[0]["label"],1)
        # Unmodified historical research workflow remains backward compatible.
        no_gate=finalize_queue(self.fixture.queue_file,self.fixture.reviews_file,
                               self.fixture.protocol_file)
        self.assertEqual(no_gate[1]["source_receipt_gate"],"not_requested")

    def test_missing_source_receipts_block_strict_export(self):
        self.one(self.fixture.decisions[0]["case_id"],"label")
        result=self.audit()
        self.assertFalse(result["structurally_receipt_complete"])
        self.assertEqual(len(result["missing_or_invalid"]),13)
        with self.assertRaisesRegex(ValueError,"strict source receipt gate failed"):
            self.strict()

    def test_tampered_archived_source_refused_even_when_receipt_claims_match(self):
        saved=self.all()
        victim=self.store/"blobs"/(saved[0]["blob_sha256"]+".bin")
        victim.write_text("FAKE modified record",encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"SHA-256|byte length mismatch"):
            self.audit()

    def test_edited_receipt_metadata_refused(self):
        saved=self.all()
        receipt=self.store/"receipts"/(saved[0]["receipt_id"]+".json")
        data=json.loads(receipt.read_text())
        data["source_record_id"]="incorrect-identity"
        receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,"content integrity mismatch"):
            self.strict()

    def test_snapshot_after_review_does_not_retroactively_validate_evidence(self):
        self.all()
        entry=self.fixture.decisions[0]
        target=next(r for r in self.audit()["review_bindings"]
                    if r["case_id"]==entry["case_id"] and r["role"]=="label")
        source=self.store/"receipts"/(target["receipt_id"]+".json")
        source.unlink()
        self.one(entry["case_id"],"label",captured_at="2026-10-12T14:00:00Z")
        result=self.audit()
        self.assertFalse(result["structurally_receipt_complete"])
        self.assertTrue(any(r["reason"]=="source_not_captured_by_review_time"
                            for r in result["missing_or_invalid"]))

    def test_negative_receipt_wrong_region_and_coverage_interval_rejected(self):
        target=next(x for x in self.fixture.decisions if x["label"] == 0)
        receipt=self.one(target["case_id"],"coverage",
                         extra={"coverage_region_id":"unrelated-region"})
        self.assertEqual(receipt["coverage_region_id"],"unrelated-region")
        result=self.audit()
        self.assertIn("scope_does_not_support_declared_negative_window",
                      [x["reason"] for x in result["missing_or_invalid"]])

    def test_wrong_original_source_record_rejected_for_label(self):
        entry=self.fixture.decisions[0]
        self.one(entry["case_id"],"label",extra={"source_record_id":"not-the-verified-record"})
        result=self.audit()
        self.assertIn("source_record_does_not_match_reviewed_label",
                      [x["reason"] for x in result["missing_or_invalid"]])

    def test_archive_idempotence_and_operator_provenance_limit(self):
        entry=self.fixture.decisions[0]
        a=self.one(entry["case_id"],"label")
        b=self.one(entry["case_id"],"label")
        self.assertEqual(a["receipt_id"],b["receipt_id"])
        self.assertFalse(a["source_authenticity_independently_verified"])
        self.assertEqual(len(list((self.store/"receipts").glob("*.json"))),1)
        data=self.root/"danger.txt"
        data.write_text("data")
        meta=self.root/"bad.json"
        meta.write_text(json.dumps({"schema_version":1,"case_id":"frame:test",
            "role":"coverage","source_url":"https://example.org/evidence",
            "rights_url":"https://example.org/license","source_record_id":"source-1",
            "source_kind":"thermal_detection", "source_published_at":PUBLISHED,
            "coverage_region_id":"region-1","coverage_start_at":"2017-01-01T00:00:00Z",
            "coverage_end_at":"2017-02-01T00:00:00Z"}))
        with self.assertRaisesRegex(ValueError,"not independently verified"):
            capture(data,meta,self.store,captured_at=CAPTURED)

    def test_cli_source_capture_audit_and_finalization(self):
        entry=self.fixture.decisions[0]
        self.all()
        report=self.root/"receipt-audit.json"
        cmd=[sys.executable,"-m","fire_public.evidence_receipts","audit",
             "--store",str(self.store),"--queue",str(self.fixture.queue_file),
             "--reviews",str(self.fixture.reviews_file),"--output",str(report)]
        done=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertTrue(json.loads(report.read_text())["structurally_receipt_complete"])
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        outputs=[self.root/x for x in ("strict-cohort.jsonl","strict-manifest.json",
                                      "strict-summary.json")]
        cli=[sys.executable,"-m","fire_public.label_review","finalize",
             "--queue",str(self.fixture.queue_file),
             "--reviews",str(self.fixture.reviews_file),
             "--protocol",str(self.fixture.protocol_file),
             "--cohort",str(outputs[0]),"--manifest",str(outputs[1]),
             "--summary",str(outputs[2]),"--evidence-store",str(self.store)]
        done=subprocess.run(cli,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual(json.loads(outputs[1].read_text())["source_receipt_gate"],
                         "hash_checked_operator_captured_snapshots")
        self.assertEqual(len(outputs[0].read_text().splitlines()),4)


if __name__=="__main__":
    unittest.main()
