"""Actual SQLite-to-source refresh-to-immutable-context integration tests.

The provider is mocked, and the saved transport claim remains explicitly
unverified outside the original network process. No wildfire labels produced.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.official_context_archive import (
    archive_context,audit_context,validate_context,
)
from test_official_lead_refresh import LeadLiveAuditTests


class OfficialContextTests(unittest.TestCase):
    def setUp(self):
        fixture=LeadLiveAuditTests("test_reconcile_original_real_archive_exact_ids_and_bytes")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture=fixture
        self.root=fixture.root
        self.queue=fixture.queue_path
        self.archive=fixture.db
        self.store=self.root/"private-evidence"
        self.store.mkdir()
        self.report,self.raw=fixture.verify()

    def save(self):
        return archive_context(self.queue,self.report,self.raw,self.store)

    def test_full_archive_and_replay_without_ground_truth_promotion(self):
        outcome=self.save()
        self.assertEqual(outcome["official_leads"],4)
        self.assertEqual(outcome["raw_pages"],2)
        self.assertEqual(outcome["valid_binary_outcomes_created"],0)
        self.assertEqual(outcome["transport_claim"],"injected_test_transport")
        audited=audit_context(self.queue,self.store)
        self.assertTrue(audited["official_source_context_consistent"])
        self.assertEqual(audited["official_leads"],4)
        self.assertEqual(audited["verified_raw_source_pages"],2)
        self.assertEqual(audited["valid_negative_labels_created"],0)
        self.assertTrue(all(not f["independent_outcome_verified"]
                            for f in audited["case_findings"]))
        self.assertEqual(len(list((self.store/"official-context/blobs").iterdir())),2)
        self.assertFalse((self.store/"receipts").exists())
        self.assertEqual(self.save(),outcome)

    def test_original_response_tampering_fails_hash_integrity(self):
        self.save()
        filename=next((self.store/"official-context/blobs").iterdir())
        filename.write_bytes(b'{"type":"FeatureCollection","features":[]}')
        with self.assertRaisesRegex(ValueError,"SHA-256 mismatch"):
            audit_context(self.queue,self.store)

    def test_manifest_tampering_fails_even_if_json_valid(self):
        saved=self.save()
        path=self.store/"official-context/runs"/(saved["archive_run_sha256"]+".json")
        payload=json.loads(path.read_text())
        payload["source_url"]="https://untrusted.example"
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,"manifest SHA-256"):
            audit_context(self.queue,self.store)

    def test_corrupted_original_queue_rejected(self):
        self.save()
        queue=json.loads(self.queue.read_text())
        queue["cases"][0]["source_name"]="changed event"
        self.queue.write_text(json.dumps(queue))
        with self.assertRaisesRegex(ValueError,"another review queue"):
            audit_context(self.queue,self.store)

    def test_rewrite_source_feature_hash_is_rejected(self):
        bad=json.loads(json.dumps(self.report))
        bad["findings"][0]["fresh_feature_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"polygon bytes contradict"):
            validate_context(self.queue,bad,self.raw)

    def test_silent_binary_label_promotion_refused(self):
        altered=json.loads(json.dumps(self.report))
        altered["findings"][0]["independent_binary_outcome_verified"]=True
        with self.assertRaisesRegex(ValueError,"must not be promoted"):
            validate_context(self.queue,altered,self.raw)
        altered=json.loads(json.dumps(self.report))
        altered["findings"][0]["negative_label_created"]=True
        with self.assertRaisesRegex(ValueError,"must not be promoted"):
            validate_context(self.queue,altered,self.raw)

    def test_missing_or_repeated_source_bytes_fail_before_archiving(self):
        names=list(self.raw)
        with self.assertRaisesRegex(ValueError,"does not cover|duplicate or absent"):
            validate_context(self.queue,self.report,{names[0]:self.raw[names[0]]})
        forged=dict(self.raw)
        forged[names[0]]=b'{"type":"FeatureCollection","features":[]}'
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            validate_context(self.queue,self.report,forged)
        self.assertFalse((self.store/"official-context").exists())

    def test_source_revision_verified_in_context_not_spread_claim(self):
        self.fixture.provider.revised=True
        report,raw=self.fixture.verify()
        archived=archive_context(self.queue,report,raw,self.store)
        result=audit_context(self.queue,self.store,run_sha256=archived["archive_run_sha256"])
        changed=[f for f in result["case_findings"]
                 if f["source_record_status"]=="source_revision_since_archival"]
        self.assertEqual(len(changed),1)
        self.assertFalse(changed[0]["independent_outcome_verified"])
        self.assertEqual(result["valid_binary_outcomes_created"],0)

    def test_cli_reaudit_and_exclusive_output_protection(self):
        result=self.save()
        filename=self.root/"audit.json"
        cmd=[sys.executable,"-m","fire_public.official_context_archive",
             "--queue",str(self.queue),"--store",str(self.store),
             "--run-sha256",result["archive_run_sha256"],
             "--output",str(filename)]
        process=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(process.returncode,0,process.stderr)
        payload=json.loads(filename.read_text())
        self.assertEqual(payload["official_leads"],4)
        self.assertEqual(payload["transport_claim"],"injected_test_transport")
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        forbidden=cmd[:]
        forbidden[-1]=str(self.queue)
        self.assertNotEqual(subprocess.run(forbidden,capture_output=True).returncode,0)

    def test_store_must_exist_and_be_private(self):
        missing=self.root/"no-created-store"
        with self.assertRaisesRegex(ValueError,"create private"):
            archive_context(self.queue,self.report,self.raw,missing)
        self.assertFalse(missing.exists())


if __name__=="__main__":
    unittest.main()
