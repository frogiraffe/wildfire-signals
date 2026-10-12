"""Test region-time negative admissibility against *archived* source receipts.

All source documents, negative labels and geography in tests are synthetic.
These tests prove contract enforcement, never genuine wildfire absence.
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

from fire_public.label_review import finalize_queue
from fire_public.negative_coverage_gate import admit_coverage,bbox
from test_evidence_receipts import EvidenceReceiptTests

CAPTURE="2026-10-12T12:00:00Z"


class NegativeCoverageGateTests(unittest.TestCase):
    def setUp(self):
        fixture=EvidenceReceiptTests("test_all_receipts_bind_then_export_statistically_structural_cohort")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.source=fixture
        self.fixture=fixture.fixture
        self.root=fixture.root
        self.store=fixture.store
        self.queue=self.fixture.queue_file
        self.reviews=self.fixture.reviews_file
        self.protocol=self.fixture.protocol_file
        # Augment existing, truly SHA-audited review queue with explicit
        # complete geographic footprint for each frame unit.
        for item in self.fixture.queue["cases"]:
            if item["kind"]=="independent_frame_review":
                x=item["longitude"];y=item["latitude"]
                item["study_bbox"]=[x-.10,y-.10,x+.10,y+.10]
        self.queue.write_text(json.dumps(self.fixture.queue),encoding="utf-8")
        self.fixture.reviews["queue_sha256"]=hashlib.sha256(self.queue.read_bytes()).hexdigest()
        self.fixture.save_reviews()
        self.source.all()
        self.registry=self.root/"coverage-registry.json"
        self.records=[]
        for entry in self.fixture.decisions:
            if entry["label"]!=0:
                continue
            cid=entry["case_id"]
            case=next(x for x in self.fixture.queue["cases"] if x["case_id"]==cid)
            self.records.append({
                "region_id":entry["region_id"],
                "provider_id":"research-fixture-independent-registry",
                "source_url":entry["negative_coverage"]["completeness_evidence_url"],
                "rights_url":"https://example.org/rights",
                "source_record_id":entry["label_source_id"],
                "coverage_bbox":[case["longitude"]-.3,case["latitude"]-.3,
                                 case["longitude"]+.3,case["latitude"]+.3],
                "inclusion_protocol":"Synthetic fixture independent registry full-window declaration",
                "windows":[{
                    "start_at":f"{entry['region_id'].split('-')[-1]}-07-04T00:00:00Z",
                    "end_at":f"{entry['region_id'].split('-')[-1]}-07-08T00:00:00Z",
                    "status":"declared_complete",
                }],
            })
        self.save()

    def save(self):
        self.registry.write_text(json.dumps({"schema_version":1,
            "areas":self.records}),encoding="utf-8")

    def audit(self):
        self.save()
        return admit_coverage(self.queue,self.reviews,self.protocol,
                              self.registry,self.store)

    def test_full_region_and_timeline_declared_scope_passes_structural_gate(self):
        result=self.audit()
        self.assertTrue(result["structurally_complete"])
        self.assertEqual(result["negative_cases_checked"],2)
        self.assertEqual(result["admitted_declarations"],2)
        self.assertEqual(result["denied"],0)
        self.assertFalse(result["independent_nonfire_truth_verified"])
        self.assertTrue(result["registry_claims_operator_supplied"])
        self.assertTrue(all(x["admission"]=="declared_scope_structurally_complete"
                            for x in result["cases"]))
        rows,manifest,summary=finalize_queue(
            self.queue,self.reviews,self.protocol,
            evidence_store=self.store,coverage_registry=self.registry)
        self.assertEqual(len(rows),4)
        self.assertEqual(manifest["negative_registry_scope_gate"],
                         "operator_declared_scope_checked_against_archived_source")
        self.assertEqual(summary["negative_registry_scope_cases_checked"],2)
        self.assertFalse(summary["negative_registry_independent_completeness_verified"])
        self.assertEqual(len(manifest["source_receipt_bindings"]),14)

    def test_missing_complete_frame_footprint_never_passes(self):
        for case in self.fixture.queue["cases"]:
            if case["kind"]=="independent_frame_review":
                del case["study_bbox"]
        self.queue.write_text(json.dumps(self.fixture.queue))
        self.fixture.reviews["queue_sha256"]=hashlib.sha256(self.queue.read_bytes()).hexdigest()
        self.fixture.save_reviews()
        result=self.audit()
        self.assertEqual(result["denied"],2)
        self.assertIn("frame_footprint_missing_or_invalid",result["cases"][0]["reasons"])

    def test_outage_overrides_even_covered_nominal_window(self):
        self.records[0]["windows"].append({
            "start_at":"2017-07-05T03:00:00Z",
            "end_at":"2017-07-05T04:00:00Z",
            "status":"reported_gap"})
        result=self.audit()
        self.assertEqual(result["denied"],1)
        self.assertTrue(any("outage_or_unknown_interval_intersects_prediction_window"
                            in x["reasons"] for x in result["cases"]))
        with self.assertRaisesRegex(ValueError,"spatial/temporal scope gate failed"):
            finalize_queue(self.queue,self.reviews,self.protocol,
                           evidence_store=self.store,coverage_registry=self.registry)

    def test_unknown_window_overrides_complete(self):
        self.records[0]["windows"].append({
            "start_at":"2017-07-05T00:00:00Z",
            "end_at":"2017-07-06T00:00:00Z",
            "status":"unknown"})
        result=self.audit()
        self.assertEqual(result["denied"],1)

    def test_adjacent_complete_windows_join_but_gap_refused(self):
        self.records[0]["windows"]=[
            {"start_at":"2017-07-05T00:00:00Z","end_at":"2017-07-05T12:00:00Z",
             "status":"declared_complete"},
            {"start_at":"2017-07-05T12:00:00Z","end_at":"2017-07-06T00:00:00Z",
             "status":"declared_complete"}]
        self.assertEqual(self.audit()["denied"],0)
        self.records[0]["windows"][1]["start_at"]="2017-07-05T12:01:00Z"
        result=self.audit()
        self.assertEqual(result["denied"],1)
        self.assertTrue(any("continuous_observation_window_not_established" in
                            x["reasons"] for x in result["cases"]))

    def test_not_all_geography_is_covered_by_anchor_point(self):
        case=next(c for c in self.fixture.queue["cases"]
                  if c["case_id"].endswith("2017") and c["kind"]=="independent_frame_review")
        # Original center is within provider geometry; edge of true footprint isn't.
        self.records[0]["coverage_bbox"]=[
            case["longitude"]-.05,case["latitude"]-.05,
            case["longitude"]+.05,case["latitude"]+.05]
        result=self.audit()
        self.assertEqual(result["denied"],1)
        self.assertTrue(any("frame_footprint_outside_provider_spatial_scope" in
                            x["reasons"] for x in result["cases"]))

    def test_wrong_provider_record_identity_or_source_rejected(self):
        self.records[0]["source_record_id"]="wrong-independent-record"
        self.assertEqual(self.audit()["denied"],1)
        self.records[0]["source_record_id"]=next(
            e["label_source_id"] for e in self.fixture.decisions
            if e["label"]==0 and e["region_id"]=="region-2017")
        self.records[0]["source_url"]="https://example.org/other-cover-record"
        self.assertEqual(self.audit()["denied"],1)

    def test_tampered_receipt_blocks_coverage_even_with_complete_declaration(self):
        receipt=next((self.store/"receipts").glob("*.json"))
        receipt.write_text(receipt.read_text()+" ")
        with self.assertRaisesRegex(ValueError,"content integrity mismatch"):
            self.audit()

    def test_registry_duplicate_and_bad_interval_rejected(self):
        self.records.append(copy.deepcopy(self.records[0]))
        with self.assertRaisesRegex(ValueError,"duplicate provider"):
            self.audit()
        self.records.pop()
        self.records[0]["windows"][0]["status"]="invented_no_fire"
        with self.assertRaisesRegex(ValueError,"status must be explicit"):
            self.audit()

    def test_antimeridian_unhandled_scope_fails_closed(self):
        with self.assertRaisesRegex(ValueError,"non-wrapping WGS84"):
            bbox([179,-10,-179,10],"cross date line")
        self.records[0]["coverage_bbox"]=[179,35,-179,40]
        with self.assertRaisesRegex(ValueError,"non-wrapping WGS84"):
            self.audit()

    def test_cli_report_and_does_not_overwrite_source(self):
        out=self.root/"negative-scope.json"
        cmd=[sys.executable,"-m","fire_public.negative_coverage_gate",
             "--queue",str(self.queue),"--reviews",str(self.reviews),
             "--protocol",str(self.protocol),"--registry",str(self.registry),
             "--evidence-store",str(self.store),"--output",str(out)]
        self.save()
        run=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(out.read_text())["admitted_declarations"],2)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        alt=cmd[:]
        alt[-1]=str(self.queue)
        self.assertNotEqual(subprocess.run(alt,capture_output=True).returncode,0)

    def test_strict_registry_cannot_run_without_private_receipt_store(self):
        self.save()
        with self.assertRaisesRegex(ValueError,"requires independent source evidence store"):
            finalize_queue(self.queue,self.reviews,self.protocol,
                           coverage_registry=self.registry)


if __name__=="__main__":
    unittest.main()
