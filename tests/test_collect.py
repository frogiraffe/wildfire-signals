import unittest
from datetime import datetime, timezone

from fire_public.collect import (build_snapshot, parse_cwfis_page, parse_firms_csv,
                                 parse_nifc_page)
from fire_public.publish import publish

AT = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
CSV = ("latitude,longitude,acq_date,acq_time,frp\n"
       "36.900,30.700,2026-10-09,1130,5\n"
       "36.901,30.701,2026-10-09,1135,7\n"
       "36.9,30.7,2026-10-07,1130,9\n")


class CollectTests(unittest.TestCase):
    def test_firms_pixels_aggregate_without_fire_confirmation(self):
        events = parse_firms_csv(CSV, "VIIRS_NOAA20_NRT", at=AT)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["detection_count"], 2)
        self.assertEqual(events[0]["kind"], "satellite_candidate")
        self.assertFalse(events[0]["source_agreement"])

    def test_nifc_filters_prescribed_fire_and_retains_official_identity(self):
        page = {"features": [{"attributes": {"IrwinID": "n1", "IncidentTypeCategory": "WF",
                  "IncidentName": "Alpha"}, "geometry": {"x": 30, "y": 36}},
                 {"attributes": {"IrwinID": "n2", "IncidentTypeCategory": "RX"},
                  "geometry": {"x": 30, "y": 36}}]}
        incidents = parse_nifc_page(page, at=AT)
        self.assertEqual([item["official_id"] for item in incidents], ["n1"])
        self.assertEqual(incidents[0]["kind"], "agency_incident")

    def test_cwfis_uses_properties_coordinates_in_new_layer(self):
        # GeoServer's geometry is EPSG:3978; properties expose WGS84 coordinates.
        raw = {"type":"FeatureCollection", "features":[{"geometry":{"type":"Point",
            "coordinates":[-1312706,1374104]}, "properties": {"national_fire_id":"c1",
            "agency_fire_id":"HWF-151-2026", "latitude":59.23287,
            "longitude":-119.21388,"status_date":"2026-10-07T17:56:00Z"}}]}
        incidents = parse_cwfis_page(raw, at=AT)
        self.assertEqual(len(incidents),1)
        self.assertEqual(incidents[0]["longitude"],-119.21388)
        self.assertEqual(incidents[0]["provider"],"cwfis")

    def test_partial_source_status_and_all_failure(self):
        source = "VIIRS_NOAA20_NRT"
        events = parse_firms_csv(CSV, source, at=AT)
        snapshot = build_snapshot({source: events}, [], at=AT,
                                  errors={"VIIRS_NOAA21_NRT": "TimeoutError"})
        self.assertEqual(snapshot["manifest"]["data_status"], "partial")
        self.assertEqual(snapshot["manifest"]["candidate_count"], 1)
        with self.assertRaises(RuntimeError):
            build_snapshot({}, [], at=AT, errors={"VIIRS_NOAA20_NRT": "error",
                "VIIRS_NOAA21_NRT": "error", "nifc_wfigs": "error",
                "cwfis": "error"})

    def test_publication_is_pointer_last(self):
        snapshot = build_snapshot({}, [], at=AT)
        calls = []
        publish(snapshot, lambda *args: calls.append(args))
        self.assertTrue(calls[0][0].startswith("snapshot:"))
        self.assertEqual(calls[1][0], "current")


if __name__ == "__main__":
    unittest.main()
