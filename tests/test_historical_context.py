"""Real HistoryStore-format cross-source replay without any network or fire inference."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.history import HistoryStore
from fire_public.intelligence_workbench import build_workbench, render_html
from fire_public.historical_context import archived_candidates, archived_weather_context
from fire_public.weather_pilot import FIELDS

BASE = "2026-10-12T10:00:00Z"


def record(kind, provider, source_id, observed, captured, payload):
    return {"subject_kind":kind,"provider":provider,"source_id":source_id,
            "record_type":"incident_status" if kind=="agency_incident" else
              "thermal_observation" if kind=="satellite_candidate" else "grid_forecast",
            "observed_at":observed,"captured_at":captured,
            "source_url":"https://example.org/source",
            "rights_url":"https://example.org/licence","payload":payload}


def weather_payload(latitude=0,longitude=179.9,valid="2026-10-12T06:00:00Z/PT12H",
                    value=20):
    fields = {k:{"uom":unit,"values":[{"validTime":valid,"value":v}]}
              for k,(unit,_),v in zip(FIELDS.keys(),FIELDS.values(),
                  (value,90,value+5,30,45,0))}
    return {"point":{"latitude":latitude,"longitude":longitude},
            "source_valid_times":valid,"fields":fields,
            "evidence_role":"captured_forecast_not_observation"}


class CrossSourceContextTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.agency = self.root/"agency.db"
        self.weather = self.root/"weather.db"
        self.events = HistoryStore(self.agency)
        self.wx = HistoryStore(self.weather)
        self.addCleanup(self.events.close)
        self.addCleanup(self.wx.close)

    def incident(self, source_id="fire", lon=179.9):
        return self.events.append(record(
            "agency_incident","cwfis",source_id,"2026-10-12T07:00:00Z",
            "2026-10-12T07:05:00Z",
            {"name":"Sample","latitude":0,"longitude":lon,"agency_status":"OC"}))

    def satellite(self, name="s1", observed="2026-10-12T08:00:00Z",
                  captured="2026-10-12T08:15:00Z", lon=-179.9, sources=None):
        return self.events.append(record(
            "satellite_candidate","firms",name,observed,captured,
            {"latitude":0,"longitude":lon,
             "observed_at":observed,"sources":sources or ["VIIRS_NOAA20_NRT"]}))

    def forecast(self, captured="2026-10-12T09:00:00Z",lon=179.91,
                 valid="2026-10-12T06:00:00Z/PT12H",value=20):
        return self.wx.append(record(
            "weather_forecast_snapshot","nws_grid","XYZ/1,1",
            "2026-10-12T06:00:00Z",captured,
            weather_payload(longitude=lon,valid=valid,value=value)))

    def test_satellite_as_of_cutoff_and_overlapping_snapshots(self):
        self.incident()
        self.satellite()
        self.satellite("s1",captured="2026-10-12T09:00:00Z")  # identical observation
        self.satellite("s2",observed="2026-10-12T09:00:00Z",
                       captured="2026-10-12T11:00:00Z")  # late receipt: NOT known yet
        self.events.connection.commit()
        result = build_workbench(self.agency,at=BASE,
                                 latitude=0,longitude=179.9,radius_km=50)
        satellite=result["satellite_evidence"]
        self.assertEqual(satellite["available_archive_records"],1)
        self.assertEqual(satellite["distinct_observed_cells"],1)
        self.assertEqual(satellite["cells_observed_in_multiple_hours"],0)
        self.assertTrue(satellite["no_fire_inference"])
        later=build_workbench(self.agency,at="2026-10-12T12:00:00Z",
                              latitude=0,longitude=179.9,radius_km=50)
        self.assertEqual(later["satellite_evidence"]["available_archive_records"],2)
        self.assertEqual(later["satellite_evidence"]["cells_observed_in_multiple_hours"],1)

    def test_weather_visibility_and_forecast_fields(self):
        self.incident()
        self.forecast()
        before=build_workbench(self.agency,at="2026-10-12T08:00:00Z",
                               weather_db=self.weather)
        self.assertEqual(before["incidents"][0]["weather_context"]["status"],
                         "no_as_of_valid_nearby_forecast")
        after=build_workbench(self.agency,at=BASE,weather_db=self.weather)
        context=after["incidents"][0]["weather_context"]
        self.assertEqual(context["status"],"available_forecast")
        self.assertLess(context["distance_km"],30)
        self.assertEqual(context["captured_at"],"2026-10-12T09:00:00+00:00")
        self.assertEqual(context["values"]["windSpeed"]["value"],20)
        self.assertFalse(context["model_ready"])
        html=render_html(after)
        self.assertIn("Captured NWS forecast evidence",html)
        self.assertIn("Forecast context, not on-site weather measurement",html)
        self.assertIn("Archived satellite candidates",html)

    def test_weather_time_validity_and_geographic_rejection(self):
        self.incident()
        self.forecast(valid="2026-10-12T01:00:00Z/PT3H")
        far=build_workbench(self.agency,at=BASE,weather_db=self.weather)
        self.assertEqual(far["incidents"][0]["weather_context"]["status"],
                         "no_as_of_valid_nearby_forecast")
        self.wx.append(record("weather_forecast_snapshot","nws_grid","XYZ/2,2",
            "2026-10-12T06:00:00Z","2026-10-12T09:30:00Z",
            weather_payload(latitude=40,longitude=-100)))
        still_far=build_workbench(self.agency,at=BASE,weather_db=self.weather)
        self.assertEqual(still_far["incidents"][0]["weather_context"]["status"],
                         "no_as_of_valid_nearby_forecast")

    def test_recent_valid_forecast_wins_and_missing_forecast_does_not_claim_zero(self):
        self.incident()
        self.forecast(value=20,captured="2026-10-12T08:00:00Z")
        self.forecast(value=30,captured="2026-10-12T09:00:00Z")
        report=build_workbench(self.agency,at=BASE,weather_db=self.weather)
        self.assertEqual(report["incidents"][0]["weather_context"]["values"]["windSpeed"]["value"],30)
        self.assertEqual(report["satellite_evidence"]["available_archive_records"],0)

    def test_source_no_coordinates_cannot_be_assigned_forecast(self):
        self.events.append(record("agency_incident","cwfis","unknown",
            "2026-10-12T07:00:00Z","2026-10-12T07:05:00Z",{"agency_status":"OC"}))
        self.forecast()
        report=build_workbench(self.agency,at=BASE,weather_db=self.weather)
        self.assertEqual(report["incidents"][0]["weather_context"]["status"],"event_location_missing")

    def test_invalid_windows_and_missing_weather_archive_rejected(self):
        self.incident()
        with self.assertRaises(ValueError):
            build_workbench(self.agency,at=BASE,satellite_hours=12)
        with self.assertRaises(FileNotFoundError):
            build_workbench(self.agency,at=BASE,weather_db=self.root/"absent.db")

    def test_cli_html_and_json_join(self):
        self.incident()
        self.satellite()
        self.forecast()
        self.events.connection.commit()
        self.wx.connection.commit()
        output=self.root/"report.json"
        webpage=self.root/"report.html"
        command=[sys.executable,"-m","fire_public.intelligence_workbench","report",
                 "--db",str(self.agency),"--weather-db",str(self.weather),
                 "--at",BASE,"--satellite-hours","24",
                 "--latitude","0","--longitude","179.9","--radius-km","50",
                 "--json",str(output),"--html",str(webpage)]
        completed=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)
        payload=json.loads(output.read_text())
        self.assertEqual(payload["satellite_evidence"]["available_archive_records"],1)
        self.assertEqual(payload["incidents"][0]["weather_context"]["status"],"available_forecast")
        self.assertIn("windSpeed",webpage.read_text())


if __name__ == "__main__":
    unittest.main()
