"""Prospective agency receipts stay small and preserve source failure state."""
import gzip
import json
import tempfile
import unittest
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fire_public.analysis_receipt import build_receipt, write_receipt
from fire_public.receipt_audit import audit_receipts
from fire_public.cli import maybe_write_analysis_receipt

AT = "2026-10-12T12:00:00+00:00"
SNAPSHOT = {"manifest":{"schema_version":1,"last_scan_at":AT,
    "data_status":"partial","source_errors":["cwfis"],"truncated":False},
    "incidents":[{"kind":"agency_incident","provider":"cwfis","official_id":"CA-1",
        "name":"Example","incident_kind":"active_wildland_fire","latitude":55,
        "longitude":-110,"modified_at":AT,"agency_status":"OC","last_seen_at":AT},
        {"kind":"agency_incident","provider":"nifc_wfigs","official_id":"US-1",
        "name":"Example US","incident_kind":"WF","latitude":39,
        "longitude":-100,"modified_at":AT,"last_seen_at":AT}],
    "events":[{"event_id":"do-not-archive"}],"matches":[{"event_id":"do-not-archive"}],
    "sources":[{"key":"nifc_wfigs","status":"complete","last_success_at":AT},
               {"key":"cwfis","status":"failed","last_success_at":AT}]}
ARGS = {"captured_at":"2026-10-12T12:01:00Z","run_id":"123",
        "head_sha":"a" * 40,"snapshot_key":"snapshot:" + "b" * 64}


class AnalysisReceiptTests(unittest.TestCase):
    def test_receipt_is_deterministic_and_contains_only_agency_states(self):
        first, report = build_receipt(SNAPSHOT, **ARGS)
        second, _ = build_receipt(SNAPSHOT, **ARGS)
        self.assertEqual(first,second)
        self.assertLess(len(first),128 * 1024)
        payload = json.loads(gzip.decompress(first))
        self.assertEqual(report["incident_count"],2)
        self.assertEqual(payload["source_states"]["cwfis"]["status"],"failed")
        self.assertEqual(payload["incident_count"],2)
        self.assertNotIn("events",payload)
        self.assertNotIn("matches",payload)
        self.assertNotIn("do-not-archive",json.dumps(payload))
        self.assertEqual([row["provider"] for row in payload["incidents"]],
                         ["cwfis","nifc_wfigs"])

    def test_late_capture_bad_records_and_large_cohort_fail_closed(self):
        with self.assertRaises(ValueError):
            build_receipt(SNAPSHOT, **{**ARGS,"captured_at":"2026-10-12T11:59:00Z"})
        with self.assertRaises(ValueError):
            build_receipt({**SNAPSHOT,"incidents":SNAPSHOT["incidents"] * 2},**ARGS)
        too_many = [{**SNAPSHOT["incidents"][0],"official_id":str(i)} for i in range(2001)]
        with self.assertRaises(ValueError):
            build_receipt({**SNAPSHOT,"incidents":too_many},**ARGS)
        with self.assertRaises(ValueError):
            build_receipt({**SNAPSHOT,"incidents":[{"kind":"satellite_candidate"}]},**ARGS)

    def test_write_receipt_does_not_replace_existing_output(self):
        payload, _ = build_receipt(SNAPSHOT, **ARGS)
        with tempfile.TemporaryDirectory() as temp:
            path = write_receipt(Path(temp),payload,scan_at=AT)
            self.assertEqual(path.read_bytes(),payload)
            with self.assertRaises(FileExistsError):
                write_receipt(Path(temp),payload,scan_at=AT)
            self.assertEqual(path.read_bytes(),payload)

    def test_optional_receipt_failure_cannot_fail_public_collection(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{
                "ENABLE_ANALYSIS_ARCHIVE":"true","ANALYSIS_RECEIPT_DIR":temp,
                "GITHUB_RUN_ID":"123","GITHUB_SHA":"a" * 40},clear=True):
            with patch("fire_public.cli.build_receipt",side_effect=ValueError("size budget")):
                result = maybe_write_analysis_receipt(SNAPSHOT,"snapshot:" + "b" * 64,
                    scan_at=datetime(2026,10,12,12,17,tzinfo=timezone.utc))
            self.assertEqual(result,{"status":"skipped","reason":"size budget"})
            self.assertEqual(list(Path(temp).iterdir()),[])
            with patch("fire_public.cli.build_receipt") as build:
                self.assertEqual(maybe_write_analysis_receipt(SNAPSHOT,"snapshot:" + "b" * 64,
                    scan_at=datetime(2026,10,12,13,tzinfo=timezone.utc))["status"],
                    "outside_pilot_window")
                build.assert_not_called()
            os.environ["FORCE_COLLECTION"] = "true"
            self.assertEqual(maybe_write_analysis_receipt(SNAPSHOT,"snapshot:" + "b" * 64,
                scan_at=datetime(2026,10,12,12,17,tzinfo=timezone.utc))["status"],
                "manual_repair_excluded")

    def test_enabled_pilot_window_writes_one_receipt(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{
                "ENABLE_ANALYSIS_ARCHIVE":"true","ANALYSIS_RECEIPT_DIR":temp,
                "GITHUB_RUN_ID":"123","GITHUB_SHA":"a" * 40},clear=True):
            result = maybe_write_analysis_receipt(SNAPSHOT,"snapshot:" + "b" * 64,
                scan_at=datetime(2026,10,12,12,17,tzinfo=timezone.utc),
                captured_at=datetime(2026,10,12,12,18,tzinfo=timezone.utc))
            self.assertEqual(result["status"],"written")
            self.assertEqual(result["incident_count"],2)
            self.assertEqual(len(list(Path(temp).glob("*.json.gz"))),1)

    def test_offline_audit_reports_gaps_and_failures_without_outcome_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            first,_ = build_receipt(SNAPSHOT,**ARGS)
            first_path = write_receipt(directory,first,scan_at=AT)
            later_at = "2026-10-13T00:00:00+00:00"
            later = {**SNAPSHOT,"manifest":{**SNAPSHOT["manifest"],
                "last_scan_at":later_at,"data_status":"fresh","source_errors":[]},
                "incidents":[{**row,"modified_at":later_at,"last_seen_at":later_at}
                             for row in SNAPSHOT["incidents"]],
                "sources":[{**row,"status":"deferred" if row["key"] == "nifc_wfigs"
                            else "complete"} for row in SNAPSHOT["sources"]]}
            second,_ = build_receipt(later,captured_at="2026-10-13T00:01:00Z",
                run_id="124",head_sha="a" * 40,snapshot_key="snapshot:" + "c" * 64)
            write_receipt(directory,second,scan_at=later_at)
            report = audit_receipts(directory)
            self.assertEqual(report["receipt_count"],2)
            self.assertEqual(report["gaps_over_9_hours"][0]["hours"],12)
            self.assertEqual(report["source_failure_counts"],{"cwfis":1})
            self.assertEqual(report["source_deferred_counts"],{"nifc_wfigs":1})
            self.assertEqual(report["identities_seen_in_2_or_more_receipts"],2)
            self.assertEqual(report["extinguishment_labels_created"],0)
            first_path.write_bytes(first + b"corrupt")
            with self.assertRaisesRegex(ValueError,"checksum"):
                audit_receipts(directory)


if __name__ == "__main__":
    unittest.main()
