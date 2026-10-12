"""Decision-time inputs must exclude retrospectively fetched evidence."""
import tempfile
import unittest
from pathlib import Path

from fire_public.decision_evidence import audit_decision
from fire_public.history import HistoryStore


class DecisionEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.event_db = Path(temp.name) / "events.sqlite3"
        self.weather_db = Path(temp.name) / "weather.sqlite3"
        self.events = HistoryStore(self.event_db)
        self.weather = HistoryStore(self.weather_db)
        self.addCleanup(self.events.close)
        self.addCleanup(self.weather.close)
        self.agency = {"subject_kind":"agency_incident", "provider":"nifc_wfigs",
            "source_id":"fire-1", "record_type":"incident_status",
            "observed_at":"2026-10-12T01:00:00Z", "captured_at":"2026-10-12T01:05:00Z",
            "source_url":"https://example.org/fire-1", "rights_url":"https://example.org/terms",
            "payload":{"latitude":39.7456,"longitude":-97.0892,"status":"active"}}
        self.forecast = {"subject_kind":"weather_forecast_snapshot", "provider":"nws_grid",
            "source_id":"TOP/32,81", "record_type":"grid_forecast",
            "observed_at":"2026-10-12T01:00:00Z", "captured_at":"2026-10-12T01:30:00Z",
            "source_url":"https://api.weather.gov/gridpoints/TOP/32,81",
            "rights_url":"https://www.weather.gov/documentation/services-web-api",
            "payload":{"point":{"latitude":39.7456,"longitude":-97.0892},
                       "source_valid_times":"2026-10-12T01:00:00Z/P1D",
                       "fields":{name:{"uom":unit,"values":[{
                           "validTime":"2026-10-12T01:00:00Z/P1D","value":value}]}
                           for name,unit,value in (("windSpeed","wmoUnit:km_h-1",20),
                                                   ("temperature","wmoUnit:degC",25),
                                                   ("relativeHumidity","wmoUnit:percent",40))},
                       "evidence_role":"captured_forecast_not_observation"}}

    def audit(self, at):
        return audit_decision(self.event_db, self.weather_db, provider="nifc_wfigs",
            source_id="fire-1", decision_at=at, weather_source_id="TOP/32,81")

    def test_later_agency_and_weather_receipts_are_not_model_inputs(self):
        self.events.append({**self.agency,"captured_at":"2026-10-12T03:00:00Z"})
        self.weather.append(self.forecast)
        result = self.audit("2026-10-12T02:00:00Z")
        self.assertEqual(result["agency_observation_ids"],[])
        self.assertIsNone(result["weather_observation_id"])
        self.assertIn("agency_not_yet_received",result["exclusions"])
        self.assertFalse(result["joint_input_available"])

    def test_explicit_weather_context_waits_for_receipt_and_excludes_later_perimeter(self):
        first = self.events.append(self.agency)
        weather_id = self.weather.append(self.forecast)
        self.events.append({**self.agency,"record_type":"perimeter_observation",
            "observed_at":"2026-10-12T01:02:00Z", "captured_at":"2026-10-12T03:00:00Z",
            "payload":{"geometry":"later perimeter"}})
        early = self.audit("2026-10-12T01:15:00Z")
        self.assertEqual(early["agency_observation_ids"],[first])
        self.assertIsNone(early["weather_observation_id"])
        self.assertIn("weather_not_yet_received",early["exclusions"])
        ready = self.audit("2026-10-12T02:00:00Z")
        self.assertEqual(ready["agency_observation_ids"],[first])
        self.assertEqual(ready["weather_observation_id"],weather_id)
        self.assertEqual(ready["distance_km"],0)
        self.assertTrue(ready["joint_input_available"])
        self.assertFalse(ready["model_ready"])

    def test_distant_weather_and_unknown_agency_point_fail_location_gate(self):
        self.events.append(self.agency)
        self.weather.append({**self.forecast,"payload":{"point":{
            "latitude":45,"longitude":-75}}})
        distant = self.audit("2026-10-12T02:00:00Z")
        self.assertIn("weather_point_too_far",distant["exclusions"])
        self.assertIsNone(distant["weather_observation_id"])
        self.assertGreater(distant["distance_km"],5)
        self.events.append({**self.agency,"source_id":"fire-2",
                            "payload":{"status":"active"}})
        unknown = audit_decision(self.event_db,self.weather_db,provider="nifc_wfigs",
            source_id="fire-2",decision_at="2026-10-12T02:00:00Z",
            weather_source_id="TOP/32,81")
        self.assertIn("agency_location_unknown",unknown["exclusions"])

    def test_forecast_without_decision_time_values_is_excluded(self):
        self.events.append(self.agency)
        self.weather.append({**self.forecast,"payload":{
            **self.forecast["payload"],"fields":{}}})
        report = self.audit("2026-10-12T02:00:00Z")
        self.assertIn("weather_validity_missing",report["exclusions"])
        self.assertIsNone(report["weather_observation_id"])

    def test_forecast_with_wrong_unit_is_excluded(self):
        self.events.append(self.agency)
        fields = {**self.forecast["payload"]["fields"],"windSpeed":{
            **self.forecast["payload"]["fields"]["windSpeed"],"uom":"wmoUnit:kn"}}
        self.weather.append({**self.forecast,"payload":{
            **self.forecast["payload"],"fields":fields}})
        self.assertIn("weather_validity_missing",
            self.audit("2026-10-12T02:00:00Z")["exclusions"])

    def test_legacy_archive_is_audited_without_schema_migration_or_write(self):
        self.events.append(self.agency)
        self.weather.append(self.forecast)
        self.events.connection.execute("DROP TABLE fire_event_sources")
        self.events.connection.execute("DROP TABLE fire_events")
        self.events.connection.commit()
        report = self.audit("2026-10-12T02:00:00Z")
        self.assertTrue(report["joint_input_available"])
        self.assertTrue(report["fire_event_id"].startswith("fire_event:"))
        self.assertIsNone(self.events.connection.execute("""
            SELECT 1 FROM sqlite_master WHERE name = 'fire_event_sources'
        """).fetchone())


if __name__ == "__main__":
    unittest.main()
