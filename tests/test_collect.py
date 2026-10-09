import unittest
import gzip
from datetime import datetime, timezone

from fire_public.collect import (build_snapshot, parse_cwfis_page, parse_firms_csv,
                                 parse_nifc_page, provisional_matches)
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
            "longitude":-119.21388,"status_date":"2026-10-07T17:56:00Z",
            "stage_of_control_status":"UC"}}]}
        incidents = parse_cwfis_page(raw, at=AT)
        self.assertEqual(len(incidents),1)
        self.assertEqual(incidents[0]["longitude"],-119.21388)
        self.assertEqual(incidents[0]["provider"],"cwfis")
        self.assertEqual(incidents[0]["modified_at"],"2026-10-07T17:56:00Z")

    def test_cwfis_excludes_extinguished_incidents(self):
        raw = {"type":"FeatureCollection", "features":[{"properties":{
            "national_fire_id":"old", "latitude":55, "longitude":-115,
            "stage_of_control_status":"EX"}}]}
        self.assertEqual(parse_cwfis_page(raw, at=AT), [])

    def test_partial_source_status_and_all_failure(self):
        source = "VIIRS_NOAA20_NRT"
        events = parse_firms_csv(CSV, source, at=AT)
        snapshot = build_snapshot({source: events}, [], at=AT,
                                  errors={"VIIRS_NOAA21_NRT": "TimeoutError"})
        self.assertEqual(snapshot["manifest"]["data_status"], "partial")
        self.assertEqual(snapshot["manifest"]["candidate_count"], 1)
        later = build_snapshot({}, [], at=AT.replace(hour=13), previous=snapshot,
                               errors={"VIIRS_NOAA20_NRT":"TimeoutError"})
        health = {row["key"]:row for row in later["sources"]}
        self.assertEqual(health["VIIRS_NOAA20_NRT"]["age_seconds"],3600)
        self.assertEqual(health["VIIRS_NOAA20_NRT"]["consecutive_failures"],1)
        delayed = build_snapshot({}, [], at=AT, errors={"cwfis":"SourceDeferred"})
        self.assertEqual({row["key"]:row for row in delayed["sources"]}["cwfis"]["status"],
                         "deferred")
        with self.assertRaises(RuntimeError):
            build_snapshot({}, [], at=AT, errors={"VIIRS_NOAA20_NRT": "error",
                "VIIRS_NOAA21_NRT": "error", "nifc_wfigs": "error",
                "cwfis": "error"})

    def test_publication_is_pointer_last(self):
        snapshot = build_snapshot({}, [], at=AT)
        calls = []
        publish(snapshot, lambda *args: calls.append(args))
        self.assertTrue(calls[0][0].startswith("snapshot:"))
        self.assertEqual(gzip.decompress(calls[0][1])[:1],b'{')
        self.assertEqual(calls[1][0], "current")

    def test_nearby_agency_point_is_only_provisional(self):
        events = [{"event_id":"e1", "latitude":36.9, "longitude":30.7,
                   "observed_at":AT.isoformat()}]
        incidents = [{"provider":"agency", "official_id":"i1", "latitude":36.91,
                      "longitude":30.71, "modified_at":AT.isoformat()}]
        links = provisional_matches(events, incidents)
        self.assertEqual(len(links),1)
        self.assertEqual(links[0]["status"],"provisional")
        incidents.append({"provider":"agency", "official_id":"i2", "latitude":36.91,
                          "longitude":30.72, "modified_at":AT.isoformat()})
        self.assertEqual({x["status"] for x in provisional_matches(events, incidents)},
                         {"ambiguous"})

    def test_old_agency_status_does_not_match_new_satellite_candidate(self):
        events = [{"event_id":"e1", "latitude":36.9,"longitude":30.7,
                   "observed_at":AT.isoformat()}]
        incidents = [{"provider":"agency", "official_id":"old", "latitude":36.9,
                      "longitude":30.7,"modified_at":"2020-05-01T00:00:00Z"}]
        self.assertEqual(provisional_matches(events, incidents), [])


if __name__ == "__main__":
    unittest.main()
