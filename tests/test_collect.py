import unittest
import gzip
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fire_public.collect import (build_snapshot, fetch_firms, parse_cwfis_page, parse_firms_csv,
                                 parse_nifc_page, provisional_matches)
from fire_public.publish import publish

AT = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
CSV = ("latitude,longitude,acq_date,acq_time,frp\n"
       "36.900,30.700,2026-10-09,1130,5\n"
       "36.901,30.701,2026-10-09,1135,7\n"
       "36.9,30.7,2026-10-05,1130,9\n")


class CollectTests(unittest.TestCase):
    def test_three_day_window_crosses_four_utc_dates(self):
        at = datetime(2026, 10, 10, 0, 55, tzinfo=timezone.utc)
        csv = ("latitude,longitude,acq_date,acq_time,frp\n"
               "36.900,30.700,2026-10-07,0100,5\n"
               "36.901,30.701,2026-10-07,0054,7\n")
        urls = []

        def fake_get(url):
            urls.append(url)
            return csv.encode()

        with patch("fire_public.collect._get", side_effect=fake_get):
            events = fetch_firms("test-key", "VIIRS_NOAA20_NRT", at=at)

        self.assertEqual(urls, ["https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
                                "test-key/VIIRS_NOAA20_NRT/world/4"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["detection_count"], 1)

    def test_midnight_collection_requests_yesterday_and_keeps_rolling_window(self):
        at = datetime(2026, 10, 10, 0, 55, tzinfo=timezone.utc)
        csv = ("latitude,longitude,acq_date,acq_time,frp\n"
               "36.900,30.700,2026-10-09,2330,5\n"
               "36.901,30.701,2026-10-06,2330,7\n")
        urls = []

        def fake_get(url):
            urls.append(url)
            return csv.encode()

        with patch("fire_public.collect._get", side_effect=fake_get):
            events = fetch_firms("test-key", "VIIRS_NOAA20_NRT", at=at)

        self.assertEqual(urls, ["https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
                                "test-key/VIIRS_NOAA20_NRT/world/4"])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["detection_count"], 1)

    def test_firms_pixels_aggregate_without_fire_confirmation(self):
        events = parse_firms_csv(CSV, "VIIRS_NOAA20_NRT", at=AT)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["detection_count"], 2)
        self.assertEqual(events[0]["kind"], "satellite_candidate")
        self.assertFalse(events[0]["source_agreement"])

    def test_same_cell_from_two_sensors_records_source_agreement_without_confirmation(self):
        first = parse_firms_csv(CSV, "VIIRS_NOAA20_NRT", at=AT)
        second = parse_firms_csv(CSV, "VIIRS_NOAA21_NRT", at=AT)
        snapshot = build_snapshot({"VIIRS_NOAA20_NRT":first,
                                   "VIIRS_NOAA21_NRT":second},[],at=AT)
        event = snapshot['events'][0]
        self.assertEqual(event['sources'],['VIIRS_NOAA20_NRT','VIIRS_NOAA21_NRT'])
        self.assertTrue(event['source_agreement'])
        self.assertEqual(event['kind'],'satellite_candidate')
        self.assertEqual(event['detection_count'],4)
        repeated = build_snapshot({"VIIRS_NOAA20_NRT":first},[],at=AT,
                                  previous=snapshot,errors={"VIIRS_NOAA21_NRT":"timeout"})
        self.assertEqual(repeated['events'][0]['detection_count'],4)

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
        self.assertEqual(__import__("json").loads(calls[-1][1])["last_scan_at"],
                         snapshot["manifest"]["last_scan_at"])
        self.assertTrue(calls[0][0].startswith("snapshot:"))
        self.assertEqual(gzip.decompress(calls[0][1])[:1],b'{')
        self.assertEqual(calls[1][0], "current")

    def test_agency_record_timeline_tracks_seen_changes_not_fire_growth(self):
        first = {"kind": "agency_incident", "provider": "cwfis", "official_id": "CA-1",
                 "name": "Example", "incident_kind": "active_wildland_fire",
                 "latitude": 52.0, "longitude": -115.0,
                 "modified_at": "2026-10-12T11:00:00+00:00", "agency_status": "UC",
                 "last_seen_at": AT.isoformat()}
        initial = build_snapshot({}, [first], at=AT)
        key = "cwfis:CA-1"
        self.assertEqual(initial["details"]["incident_history"][key][0]["change"], "first_seen")
        unchanged = build_snapshot({}, [{**first, "last_seen_at": AT.replace(hour=13).isoformat()}],
                                   at=AT.replace(hour=13), previous=initial)
        self.assertEqual(len(unchanged["details"]["incident_history"][key]), 1)
        updated = build_snapshot({}, [{**first, "agency_status": "BH",
            "modified_at": "2026-10-12T13:30:00+00:00"}],
            at=AT.replace(hour=14), previous=unchanged)
        history = updated["details"]["incident_history"][key]
        self.assertEqual([item["change"] for item in history], ["first_seen", "record_changed"])
        self.assertEqual([item["agency_status"] for item in history], ["UC", "BH"])
        failed = build_snapshot({}, [], at=AT.replace(hour=15), previous=updated,
                                errors={"cwfis": "TimeoutError"})
        self.assertEqual(failed["details"]["incident_history"][key], history)

    def test_unchanged_incident_does_not_gain_false_first_seen_after_72_hours(self):
        incident = {"kind": "agency_incident", "provider": "cwfis", "official_id": "CA-1",
                    "name": "Example", "incident_kind": "active_wildland_fire",
                    "latitude": 52.0, "longitude": -115.0,
                    "modified_at": "2026-10-12T11:00:00+00:00", "agency_status": "UC",
                    "last_seen_at": AT.isoformat()}
        first = build_snapshot({}, [incident], at=AT)
        key = "cwfis:CA-1"
        later_at = AT + timedelta(hours=73)
        failed = build_snapshot({}, [], at=later_at, previous=first,
                                errors={"cwfis": "TimeoutError"})
        self.assertEqual(failed["details"]["incident_history"][key][0]["seen_at"],
                         AT.isoformat())
        recovered = build_snapshot({}, [{**incident, "last_seen_at": later_at.isoformat()}],
                                   at=later_at + timedelta(hours=1), previous=failed)
        entries = recovered["details"]["incident_history"][key]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["seen_at"], AT.isoformat())

    def test_incident_timeline_tracks_source_location_change_and_keeps_first_entry(self):
        incident = {"kind": "agency_incident", "provider": "nifc_wfigs", "official_id": "US-1",
                    "name": "Example", "incident_kind": "WF", "latitude": 40.0,
                    "longitude": -110.0, "modified_at": AT.isoformat(),
                    "last_seen_at": AT.isoformat()}
        snapshot = build_snapshot({}, [incident], at=AT)
        key = "nifc_wfigs:US-1"
        for index in range(1, 7):
            at = AT + timedelta(hours=index)
            changed = {**incident, "longitude": -110.0 + index / 100,
                       "last_seen_at": at.isoformat()}
            snapshot = build_snapshot({}, [changed], at=at, previous=snapshot)
        entries = snapshot["details"]["incident_history"][key]
        self.assertEqual(len(entries), 5)
        self.assertEqual(entries[0]["change"], "first_seen")
        self.assertEqual(entries[0]["seen_at"], AT.isoformat())
        self.assertEqual(entries[-1]["seen_at"], (AT + timedelta(hours=6)).isoformat())

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
