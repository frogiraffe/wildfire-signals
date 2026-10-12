"""Integration tests for the end-to-end historical change explorer.

Fixture reports use the real agency receipt schema and SQLite HistoryStore.
No fixture result represents a real wildfire or model performance.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.analysis_receipt import build_receipt, write_receipt
from fire_public.history import HistoryStore
from fire_public.receipt_history import import_receipts
from fire_public.change_explorer import compare_archive, compare_reports, render_changes_html
from fire_public.intelligence_workbench import build_workbench

BASE = "2026-10-12"


def agency(official_id="CA-1", *, hour=0, status="OC", name="Test source fire"):
    stamp=f"{BASE}T{hour:02d}:17:00Z"
    return {"kind":"agency_incident","provider":"cwfis","official_id":official_id,
            "name":name,"incident_kind":"active_wildland_fire",
            "latitude":55.0,"longitude":-110.0,"modified_at":stamp,
            "last_seen_at":stamp,"agency_status":status}


def artifact(snapshot, captured_at, hour, root):
    payload,_ = build_receipt(snapshot,captured_at=captured_at,
                              run_id=str(1000+hour),head_sha="a"*40,
                              snapshot_key="snapshot:"+"b"*64)
    write_receipt(root,payload,scan_at=snapshot["manifest"]["last_scan_at"])


class HistoricalChangeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.db=self.path/"events.sqlite3"
        self.receipts=self.path/"receipts"
        self.store=HistoryStore(self.db)
        self.addCleanup(self.store.close)

    def receipt(self, hour, *, status="complete", listed=True, agency_status="OC",
                name="Test source fire", official_id="CA-1"):
        scan=f"{BASE}T{hour:02d}:17:00Z"
        capture=f"{BASE}T{hour:02d}:18:00Z"
        snapshot={
            "manifest":{"schema_version":1,"last_scan_at":scan,
                        "data_status":"fresh" if status=="complete" else "partial",
                        "source_errors":[] if status=="complete" else ["cwfis"],
                        "truncated":False},
            "sources":[{"key":"nifc_wfigs","status":"complete"},
                       {"key":"cwfis","status":status}],
            "incidents":[agency(official_id,hour=hour,status=agency_status,name=name)]
                        if listed else [],
            "events":[],"matches":[]}
        artifact(snapshot,capture,hour,self.receipts)

    def satellite(self, sid, observed, captured, *, lon=-110.0):
        self.store.append({"subject_kind":"satellite_candidate","provider":"firms",
          "source_id":sid,"record_type":"thermal_observation",
          "observed_at":observed,"captured_at":captured,
          "source_url":"https://example.org/firms","rights_url":"https://example.org/rights",
          "payload":{"latitude":55.0,"longitude":lon,
                     "observed_at":observed,"sources":["VIIRS_NOAA20_NRT"]}})

    def compare(self, **kwargs):
        return compare_archive(self.db,earlier_at=f"{BASE}T03:00:00Z",
                               later_at=f"{BASE}T09:00:00Z",**kwargs)

    def test_changed_status_and_added_archive_evidence(self):
        self.receipt(0,agency_status="OC")
        self.receipt(6,agency_status="UC")
        import_receipts(self.store,self.receipts)
        result=self.compare()
        self.assertTrue(result["comparison_untruncated"])
        self.assertEqual(len(result["agency"]["changed_events"]),1)
        event=result["agency"]["changed_events"][0]
        self.assertEqual(event["change_type"],"source_reported_status_changed")
        self.assertEqual(event["reported_status_before"],"OC")
        self.assertEqual(event["reported_status_after"],"UC")
        self.assertEqual(event["new_evidence_records_in_displayed_timeline"],1)
        self.assertEqual(result["wildfire_outcome_labels_created"],0)
        self.assertFalse(result["validated_prediction"])

    def test_source_failure_is_not_fire_termination(self):
        self.receipt(0)
        self.receipt(6,status="failed",listed=True)  # carried stale agency row
        import_receipts(self.store,self.receipts)
        result=self.compare()
        item=result["agency"]["changed_events"][0]
        self.assertEqual(item["change_type"],"source_layer_availability_changed")
        self.assertEqual(item["reported_status_before"],"OC")
        self.assertEqual(item["reported_status_after"],"OC")
        self.assertEqual(item["layer_availability_after"],"source_unavailable")
        self.assertTrue(result["sources"]["cwfis"]["changed"])
        self.assertEqual(result["wildfire_outcome_labels_created"],0)

    def test_absence_in_complete_scan_is_not_extinguishment(self):
        self.receipt(0)
        self.receipt(6,listed=False)
        import_receipts(self.store,self.receipts)
        event=self.compare()["agency"]["changed_events"][0]
        self.assertEqual(event["layer_availability_after"],
                         "not_listed_in_latest_complete_scan")
        self.assertNotEqual(event["change_type"],"fire_extinguished")

    def test_newly_archived_id_is_not_claimed_as_new_ignition(self):
        self.receipt(0,official_id="first")
        self.receipt(6,official_id="new")
        import_receipts(self.store,self.receipts)
        result=self.compare()
        new=[x for x in result["agency"]["changed_events"]
             if x["official_id"]=="new"][0]
        self.assertEqual(new["change_type"],"first_seen_in_archive")
        self.assertEqual(new["reported_status_before"],None)
        self.assertIn("not independently verified fire activity",new["note"])

    def test_later_satellite_receipt_visible_only_at_later_decision(self):
        self.receipt(0)
        import_receipts(self.store,self.receipts)
        self.satellite("a",f"{BASE}T02:00:00Z",f"{BASE}T02:10:00Z")
        self.satellite("b",f"{BASE}T05:00:00Z",f"{BASE}T08:00:00Z")
        self.satellite("c",f"{BASE}T02:00:00Z",f"{BASE}T11:00:00Z")
        result=self.compare(latitude=55,longitude=-110,radius_km=100)
        self.assertEqual(result["satellite"]["earlier"]["available_archive_records"],1)
        self.assertEqual(result["satellite"]["later"]["available_archive_records"],2)
        self.assertEqual(result["agency"]["changed_events"],[])
        self.assertIn("NOT burned-area",result["satellite"]["note"])

    def test_truncation_is_not_source_completeness(self):
        self.receipt(0,official_id="A")
        self.receipt(6,official_id="B")
        import_receipts(self.store,self.receipts)
        result=self.compare(limit=1)
        self.assertFalse(result["comparison_untruncated"])
        self.assertIn("agency_display_limit",result["incomplete_reasons"])

    def test_bad_order_and_inconsistent_scope_rejected(self):
        self.receipt(0)
        import_receipts(self.store,self.receipts)
        one=build_workbench(self.db,at=f"{BASE}T03:00:00Z")
        later=build_workbench(self.db,at=f"{BASE}T09:00:00Z")
        with self.assertRaises(ValueError):
            compare_reports(later,one)
        elsewhere=build_workbench(self.db,at=f"{BASE}T09:00:00Z",
                                   latitude=0,longitude=0,radius_km=50)
        with self.assertRaises(ValueError):
            compare_reports(one,elsewhere)

    def test_two_captured_weather_forecast_revisions_are_not_observed_weather(self):
        from fire_public.weather_pilot import FIELDS
        wxpath=self.path/"weather.sqlite3"
        wx=HistoryStore(wxpath)
        self.addCleanup(wx.close)
        self.receipt(0)
        import_receipts(self.store,self.receipts)
        for issued,captured,wind in [
                (f"{BASE}T00:00:00Z",f"{BASE}T01:00:00Z",10),
                (f"{BASE}T06:00:00Z",f"{BASE}T07:00:00Z",20)]:
            values={"windSpeed":wind,"windDirection":90,"windGust":25,
                    "temperature":20,"relativeHumidity":40,
                    "quantitativePrecipitation":0}
            fields={name:{"uom":unit,"values":[{
                "validTime":f"{BASE}T00:00:00Z/P1D",
                "value":values[name]}]} for name,(unit,_) in FIELDS.items()}
            wx.append({"subject_kind":"weather_forecast_snapshot",
                       "provider":"nws_grid","source_id":"ABC/1,2",
                       "record_type":"grid_forecast",
                       "observed_at":issued,"captured_at":captured,
                       "source_url":"https://example.org/grid",
                       "rights_url":"https://example.org/rights",
                       "payload":{"point":{"latitude":55.0,"longitude":-110.0},
                                  "source_valid_times":f"{BASE}T00:00:00Z/P1D",
                                  "fields":fields,
                                  "evidence_role":"captured_forecast_not_observation"}})
        result=self.compare(weather_db=wxpath)
        self.assertEqual(len(result["forecast_receipt_changes"]),1)
        forecast=result["forecast_receipt_changes"][0]
        self.assertEqual(forecast["before"]["captured_at"],f"{BASE}T01:00:00+00:00")
        self.assertEqual(forecast["after"]["captured_at"],f"{BASE}T07:00:00+00:00")
        self.assertIn("NOT measurements",forecast["note"])

    def test_html_escapes_archived_source_text(self):
        self.receipt(0,name="<img src=x onerror=alert(1)>")
        self.receipt(6,name="<script>alert(1)</script>",agency_status="UC")
        import_receipts(self.store,self.receipts)
        html=render_changes_html(self.compare())
        self.assertIn("&lt;script&gt;",html)
        self.assertNotIn("<script>alert(1)</script>",html)
        self.assertNotIn("<img src=x onerror",html)

    def test_cli_html_json_and_source_file_protection(self):
        self.receipt(0)
        self.receipt(6,agency_status="BH")
        import_receipts(self.store,self.receipts)
        js=self.path/"changes.json"; webpage=self.path/"changes.html"
        command=[sys.executable,"-m","fire_public.intelligence_workbench","compare",
                 "--db",str(self.db),
                 "--earlier-at",f"{BASE}T03:00:00Z","--later-at",f"{BASE}T09:00:00Z",
                 "--json",str(js),"--html",str(webpage)]
        first=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(first.returncode,0,first.stderr)
        result=json.loads(js.read_text())
        self.assertEqual(result["agency"]["changed_events"][0]["reported_status_after"],"BH")
        self.assertIn("Historical Evidence Change Explorer",webpage.read_text())
        second=subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(second.returncode,0)
        destructive=subprocess.run(command[:],capture_output=True,text=True)
        bad=command[:]
        bad[bad.index("--json")+1]=str(self.db)
        bad += ["--overwrite"]
        blocked=subprocess.run(bad,capture_output=True,text=True)
        self.assertNotEqual(blocked.returncode,0)
        self.assertIn("cannot overwrite",blocked.stderr)
        self.assertEqual(json.loads(first.stdout)["changed_events"],1)


if __name__=="__main__":
    unittest.main()
