"""Real SQLite Historical Workbench + retrospective NIFC polygon adapter tests.

No source fetch or source completeness claims; mock ArcGIS transport only.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.history import HistoryStore
from fire_public.intelligence_workbench import build_workbench, render_html
from fire_public.change_explorer import compare_archive,render_changes_html,compare_reports
from fire_public.official_perimeters import sync_year

T0="2026-10-12T09:00:00Z"
T1="2026-10-12T12:00:00Z"
T2="2026-10-13T12:00:00Z"


def shape():
    return {"type":"Polygon","coordinates":[[
        [-120.02,37.0],[-119.98,37.0],[-119.98,37.04],
        [-120.02,37.04],[-120.02,37.0]]]}


def perimeter(name):
    return {"type":"Feature","properties":{
        "OBJECTID":17,"GlobalID":"{verified-17}","FIRE_YEAR_INT":2018,
        "INCIDENT":name,"GIS_ACRES":60.0,"SOURCE":"US agency"},
        "geometry":shape()}


class MockProvider:
    def __init__(self):
        self.name="Historical <Fire>"

    def __call__(self,params):
        if params.get("returnIdsOnly")=="true":
            return {"objectIds":[17]}
        return {"type":"FeatureCollection","features":[perimeter(self.name)]}


class WorkbenchPerimeterTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.agency=self.root/"agency.sqlite3"
        self.perimeter=self.root/"nifc.sqlite3"
        self.store=HistoryStore(self.agency)
        self.addCleanup(self.store.close)
        self.store.append({
            "subject_kind":"agency_incident","provider":"cwfis",
            "source_id":"CA-independent","record_type":"incident_status",
            "observed_at":"2026-10-12T08:00:00Z","captured_at":T0,
            "source_url":"https://example.org/incident",
            "rights_url":"https://example.org/license",
            "payload":{"name":"Canadian agency event","latitude":55.0,
                       "longitude":-110.0,"agency_status":"OC"}})
        self.transport=MockProvider()

    def sync(self,clock=T1):
        return sync_year(self.perimeter,year=2018,max_records=1,
                         get_json=self.transport,clock=lambda:clock)

    def view(self,at=T2,**kwargs):
        return build_workbench(self.agency,at=at,
            perimeter_db=self.perimeter,**kwargs)

    def test_workbench_separates_as_of_retrospective_evidence_from_agency(self):
        self.sync()
        older=self.view(at="2026-10-12T10:00:00Z",perimeter_year=2018)
        future=self.view(at=T2,perimeter_year=2018)
        self.assertEqual(older["retrospective_perimeter_evidence"]["matched_polygons"],0)
        self.assertEqual(future["retrospective_perimeter_evidence"]["matched_polygons"],1)
        self.assertEqual(future["retrospective_perimeter_evidence"]["source_fire_year"],2018)
        self.assertFalse(future["retrospective_perimeter_evidence"]["model_ready"])
        self.assertEqual(future["retrospective_perimeter_evidence"]["negative_labels_created"],0)
        self.assertEqual(future["matched_identities"],1)  # Canadian agency stays independent.
        self.assertEqual(len(future["incidents"]),1)
        self.assertEqual(future["schema_version"],3)
        self.assertIn("&lt;Fire&gt;",render_html(future))

    def test_report_city_circle_and_year_never_label_negative(self):
        self.sync()
        inside=self.view(at=T2,latitude=37.02,longitude=-120,radius_km=15)
        self.assertEqual(inside["retrospective_perimeter_evidence"]["matched_polygons"],1)
        outside=self.view(at=T2,latitude=0,longitude=30,radius_km=10)
        self.assertEqual(outside["retrospective_perimeter_evidence"]["matched_polygons"],0)
        self.assertEqual(outside["retrospective_perimeter_evidence"]["negative_labels_created"],0)
        with self.assertRaises(ValueError):
            self.view(at=T2,latitude=37,longitude=-120,radius_km=400)

    def test_two_capture_times_not_contemporaneous_fire_progression(self):
        self.sync()
        older=build_workbench(self.agency,at=T0,perimeter_db=self.perimeter)
        later=self.view(at=T2)
        diff=compare_reports(older,later)
        data=diff["retrospective_perimeter_changes"]
        self.assertEqual(data["earlier_matched_polygons"],0)
        self.assertEqual(data["later_matched_polygons"],1)
        self.assertEqual(data["first_seen_or_revised_in_preview"][0]["kind"],
                         "first_seen_in_archive")
        self.assertTrue(data["no_negative_labels"])
        self.assertIn("NOT a wildfire ignition",
                      data["first_seen_or_revised_in_preview"][0]["note"])
        self.assertIn("Historical Evidence Change Explorer",render_changes_html(diff))
        self.assertIn("Retrospective perimeter",render_changes_html(diff))

    def test_source_revision_happens_at_actual_capture(self):
        self.sync()
        self.transport.name="Historical corrected perimeter"
        self.sync(clock=T2)
        diff=compare_archive(self.agency,perimeter_db=self.perimeter,
                             earlier_at=T1,later_at=T2)
        updates=diff["retrospective_perimeter_changes"]["first_seen_or_revised_in_preview"]
        self.assertEqual(len(updates),1)
        self.assertEqual(updates[0]["kind"],
                         "retrospective_source_geometry_or_attribute_revision")

    def test_backwards_compatibility_and_missing_db(self):
        baseline=build_workbench(self.agency,at=T2)
        self.assertIsNone(baseline["retrospective_perimeter_evidence"])
        self.assertEqual(len(baseline["incidents"]),1)
        with self.assertRaises(ValueError):
            build_workbench(self.agency,at=T2,perimeter_year=2018)
        with self.assertRaises(FileNotFoundError):
            build_workbench(self.agency,at=T2,
                            perimeter_db=self.root/"missing.sqlite3")

    def test_cli_report_compare_and_overwrite_guard_for_all_source_dbs(self):
        self.sync()
        runner=[sys.executable,"-m","fire_public.intelligence_workbench"]
        one=self.root/"report.json"
        html=self.root/"report.html"
        cmd=runner+["report","--db",str(self.agency),
                    "--perimeter-db",str(self.perimeter),
                    "--perimeter-year","2018","--at",T2,
                    "--json",str(one),"--html",str(html)]
        run=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(one.read_text())[
            "retrospective_perimeter_evidence"]["matched_polygons"],1)
        self.assertIn("Official retrospective US fire perimeters",html.read_text())
        changed=self.root/"compare.json"
        cmd=runner+["compare","--db",str(self.agency),
                    "--perimeter-db",str(self.perimeter),
                    "--earlier-at",T0,"--later-at",T2,
                    "--json",str(changed)]
        run=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(changed.read_text())[
            "retrospective_perimeter_changes"]["later_matched_polygons"],1)
        unsafe=cmd[:]
        unsafe[unsafe.index("--json")+1]=str(self.perimeter)
        unsafe.append("--overwrite")
        blocked=subprocess.run(unsafe,capture_output=True,text=True)
        self.assertNotEqual(blocked.returncode,0)
        self.assertIn("cannot overwrite",blocked.stderr)


if __name__=="__main__":
    unittest.main()
