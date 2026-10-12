"""End-to-end offline workbench checks using real archive and receipt formats.

Fixtures simulate provider responses; they are not measured wildfire model results.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.analysis_receipt import build_receipt, write_receipt
from fire_public.history import HistoryStore
from fire_public.intelligence_workbench import build_workbench, render_html
from fire_public.receipt_history import import_receipts


class HistoricalIntelligenceWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "archive.sqlite3"
        self.receipts = self.root / "receipts"
        self.store = HistoryStore(self.db)
        self.addCleanup(self.store.close)

    def add_receipt(self, hour, *, status="complete", incidents=None):
        scan = f"2026-10-12T{hour:02d}:17:00Z"
        capture = f"2026-10-12T{hour:02d}:18:00Z"
        snapshot = {"manifest": {"schema_version":1,"last_scan_at":scan,
                     "data_status":"partial" if status != "complete" else "fresh",
                     "source_errors":[status] if status != "complete" else [],
                     "truncated":False},
                    "sources":[{"key":"cwfis","status":status},
                               {"key":"nifc_wfigs","status":"complete"}],
                    "incidents":incidents or [],"events":[],"matches":[]}
        payload,_ = build_receipt(snapshot,captured_at=capture,run_id=str(hour+100),
                                  head_sha="a"*40,snapshot_key="snapshot:"+"b"*64)
        write_receipt(self.receipts,payload,scan_at=scan)

    @staticmethod
    def fire(name="CA-1",status="OC",lon=-110,lat=55,hour=0):
        return {"kind":"agency_incident","provider":"cwfis","official_id":name,
                "name":"Example "+name,"incident_kind":"active_wildland_fire",
                "latitude":lat,"longitude":lon,
                "modified_at":f"2026-10-12T{hour:02d}:17:00Z",
                "last_seen_at":f"2026-10-12T{hour:02d}:17:00Z",
                "agency_status":status}

    def test_complete_failure_and_absence_are_distinct(self):
        self.add_receipt(0,incidents=[self.fire()])
        self.add_receipt(6,status="failed",incidents=[self.fire()])  # stale carried row
        self.add_receipt(12)
        import_receipts(self.store,self.receipts)
        r0 = build_workbench(self.db,at="2026-10-12T03:00:00Z")
        self.assertEqual(r0["incidents"][0]["source_layer_availability"],
                         "listed_in_latest_complete_scan")
        self.assertEqual(r0["incidents"][0]["reported_status"],"OC")
        r1 = build_workbench(self.db,at="2026-10-12T09:00:00Z")
        self.assertEqual(r1["incidents"][0]["source_layer_availability"],
                         "source_unavailable")
        self.assertEqual(r1["incidents"][0]["evidence_count"],1)
        r2 = build_workbench(self.db,at="2026-10-12T15:00:00Z")
        self.assertEqual(r2["incidents"][0]["source_layer_availability"],
                         "not_listed_in_latest_complete_scan")
        self.assertEqual(r2["extinguishment_labels_created"],0)
        self.assertEqual(r2["validated_prediction"],False)

    def test_future_status_is_invisible_and_corrections_preserved(self):
        self.add_receipt(0,incidents=[self.fire(status="OC")])
        self.add_receipt(6,incidents=[self.fire(status="UC",hour=6)])
        import_receipts(self.store,self.receipts)
        first = build_workbench(self.db,at="2026-10-12T04:00:00Z")
        final = build_workbench(self.db,at="2026-10-12T08:00:00Z")
        self.assertEqual([x["reported_status"] for x in first["incidents"][0]["timeline"]],["OC"])
        self.assertEqual([x["reported_status"] for x in final["incidents"][0]["timeline"]],["OC","UC"])
        self.assertEqual(final["incidents"][0]["reported_status"],"UC")
        self.assertEqual(final["incidents"][0]["timeline"][-1]["captured_at"],
                         "2026-10-12T06:18:00+00:00")

    def test_circle_search_and_antimeridian(self):
        self.add_receipt(0,incidents=[
            self.fire("east",lon=179.9,lat=0),
            self.fire("west",lon=-179.9,lat=0),
            self.fire("distant",lon=150,lat=0),
            self.fire("missing",lon=None,lat=None)])
        import_receipts(self.store,self.receipts)
        report = build_workbench(self.db,at="2026-10-12T05:00:00Z",
                                 latitude=0,longitude=179.95,radius_km=50)
        self.assertEqual({x["official_id"] for x in report["incidents"]},{"east","west"})
        self.assertEqual(report["missing_coordinates_in_region_search"],1)
        self.assertEqual(report["outside_region"],1)

    def test_late_retrospective_evidence_never_time_travels(self):
        self.store.append({"subject_kind":"agency_incident","provider":"cwfis",
                           "source_id":"old","record_type":"incident_status",
                           "observed_at":"2019-01-01T00:00:00Z",
                           "captured_at":"2026-10-12T15:00:00Z",
                           "source_url":"https://example.org/old",
                           "rights_url":"https://example.org/license",
                           "payload":{"stage_of_control_status":"UC"}})
        self.assertEqual(build_workbench(self.db,at="2020-01-01T00:00:00Z")["shown"],0)
        late = build_workbench(self.db,at="2026-10-12T16:00:00Z")
        self.assertEqual(late["shown"],1)
        self.assertEqual(late["incidents"][0]["timeline"][0]["observed_at"],
                         "2019-01-01T00:00:00+00:00")

    def test_receipt_gaps_detected_without_inferring_fire(self):
        self.add_receipt(0,incidents=[self.fire()])
        self.add_receipt(12,incidents=[self.fire(hour=12)])
        import_receipts(self.store,self.receipts)
        report = build_workbench(self.db,at="2026-10-12T18:00:00Z")
        self.assertEqual(len(report["receipt_gaps_over_9_hours"]),1)
        self.assertGreater(report["receipt_gaps_over_9_hours"][0]["hours"],9)

    def test_read_only_does_not_create_archive_or_change_bytes(self):
        missing = self.root / "does-not-exist.sqlite3"
        with self.assertRaises(FileNotFoundError):
            build_workbench(missing,at="2026-10-12T18:00:00Z")
        self.add_receipt(0,incidents=[self.fire()])
        import_receipts(self.store,self.receipts)
        self.store.connection.commit()
        before = self.db.read_bytes()
        build_workbench(self.db,at="2026-10-12T18:00:00Z")
        self.assertEqual(self.db.read_bytes(),before)

    def test_html_escapes_untrusted_provider_text_and_links(self):
        self.store.append({"subject_kind":"agency_incident","provider":"nifc_wfigs",
                           "source_id":"evil","record_type":"incident_status",
                           "observed_at":"2026-10-01T00:00:00Z",
                           "captured_at":"2026-10-02T00:00:00Z",
                           "source_url":"javascript:alert(1)",
                           "rights_url":"https://example.org/licence",
                           "payload":{"name":"<script>alert(1)</script>","agency_status":"OC"}})
        doc = render_html(build_workbench(self.db,at="2026-10-12T18:00:00Z"))
        self.assertIn("&lt;script&gt;",doc)
        self.assertNotIn("<script>alert(1)</script>",doc)
        self.assertNotIn('href="javascript:',doc)
        self.assertIn("Missing from a complete active agency layer",doc)

    def test_bounded_input_and_region_arguments(self):
        for kwargs in ({"limit":0},{"limit":501},{"latitude":0},
                       {"latitude":100,"longitude":0,"radius_km":50},
                       {"latitude":0,"longitude":180,"radius_km":float("nan")}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                build_workbench(self.db,at="2026-10-12T18:00:00Z",**kwargs)
        with self.assertRaises(ValueError):
            build_workbench(self.db,at="2026-10-12T18:00:00")

    def test_cli_writes_both_reports_and_refuses_unintended_overwrite(self):
        self.add_receipt(0,incidents=[self.fire()])
        import_receipts(self.store,self.receipts)
        cmd = [sys.executable,"-m","fire_public.intelligence_workbench","report",
               "--db",str(self.db),"--at","2026-10-12T18:00:00Z",
               "--json",str(self.root/"report.json"),"--html",str(self.root/"report.html")]
        first = subprocess.run(cmd,capture_output=True,text=True,check=True)
        self.assertEqual(json.loads((self.root/"report.json").read_text())["shown"],1)
        self.assertIn("Historical Evidence Workbench",(self.root/"report.html").read_text())
        second = subprocess.run(cmd,capture_output=True,text=True)
        self.assertNotEqual(second.returncode,0)
        self.assertIn("output already exists",second.stderr)
        self.assertEqual(json.loads(first.stdout)["shown"],1)


if __name__=="__main__":
    unittest.main()
