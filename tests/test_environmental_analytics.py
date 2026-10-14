"""Historical station context is retrospective, with unknown satellite exposure."""
from datetime import datetime, timezone
from pathlib import Path
import csv
import hashlib
import json
import tempfile
import unittest

from fire_public.collect import FIRMS_SOURCES
from fire_public.environmental_analytics import build_station_context
from fire_public.historical_rollup import build_rollup
from fire_public.pixel_history import import_release_assets
from test_pixel_history import make_release, pixel


REGION = {"region_id": "PILOT", "latitude": 37.929, "longitude": 41.1166, "radius_km": 25}
STATION = {"id": "TUI0000LTCJ", "name": "BATMAN", "latitude": 37.929,
           "longitude": 41.1166, "elevation_m": 555.3}
FIELDS = ["STATION", "Station_name", "DATE", "LATITUDE", "LONGITUDE", "ELEVATION",
          "temperature", "temperature_Quality_Code", "wind_speed", "wind_speed_Quality_Code",
          "wind_direction", "wind_direction_Quality_Code", "relative_humidity",
          "relative_humidity_Quality_Code"]


class EnvironmentalAnalyticsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.db = root / "pixels.sqlite3"
        self.weather = root / "weather.psv"
        captured = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
        pixels = [pixel(FIRMS_SOURCES[0], when=datetime(2026, 10, 10, 10, 35,
                  tzinfo=timezone.utc), latitude=37.94, longitude=41.12, ident="one"),
                  pixel(FIRMS_SOURCES[1], when=datetime(2026, 10, 11, 9, 15,
                  tzinfo=timezone.utc), latitude=37.94, longitude=41.12, ident="two")]
        make_release(root / "scan", captured, pixels)
        import_release_assets(self.db, root)
        build_rollup(self.db, [REGION])
        records = [
            {"DATE": "2026-10-10T09:00:00", "temperature": "18.0", "wind_speed": "2.0",
             "wind_direction": "120", "relative_humidity": "65"},
            {"DATE": "2026-10-10T10:20:00", "temperature": "20.0", "wind_speed": "3.0",
             "wind_direction": "130", "relative_humidity": "60"},
            {"DATE": "2026-10-10T11:00:00", "temperature": "21.0", "wind_speed": "4.0",
             "wind_direction": "140", "relative_humidity": "55"},
            {"DATE": "2026-10-11T08:00:00", "temperature": "22.0", "wind_speed": "5.0",
             "wind_direction": "150", "relative_humidity": "50",
             "temperature_Quality_Code": "X"},
        ]
        with self.weather.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="|")
            writer.writeheader()
            for record in records:
                writer.writerow({"STATION": STATION["id"], "Station_name": STATION["name"],
                                 "LATITUDE": STATION["latitude"], "LONGITUDE": STATION["longitude"],
                                 "ELEVATION": STATION["elevation_m"], **record})

    def run_report(self):
        return build_station_context(self.db, [REGION], self.weather, STATION,
               start_date="2026-10-10", end_date="2026-10-11",
               source_url="https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2026/psv/GHCNh_TUI0000LTCJ_2026.psv",
               source_last_modified="2026-10-12T12:53:32+00:00")

    def test_join_uses_prior_station_record_and_leaves_uncovered_hour_unknown(self):
        report = self.run_report()
        rows = {row["observed_hour"]: row for row in report["candidate_hours"]}
        self.assertEqual(rows["2026-10-10T10:00:00+00:00"]["temperature_c"], 18.0)
        self.assertEqual(rows["2026-10-10T10:00:00+00:00"]["weather_observed_at"],
                         "2026-10-10T09:00:00+00:00")
        self.assertIsNone(rows["2026-10-11T09:00:00+00:00"]["temperature_c"])
        self.assertEqual(report["population"]["matched_candidate_hours_temperature_c"], 1)
        self.assertEqual(report["population"]["candidate_hours"], 2)
        self.assertFalse(report["observation_opportunity_verified"])
        self.assertIsNone(report["environment_first_available_at"])
        self.assertEqual(report, self.run_report())

    def test_weather_file_hash_and_station_identity_are_checked(self):
        report = self.run_report()
        self.assertEqual(len(report["source_sha256"]), 64)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_station_context(self.db, [REGION], self.weather, STATION,
                start_date="2026-10-10", end_date="2026-10-11",
                source_url="https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2026/psv/GHCNh_TUI0000LTCJ_2026.psv",
                source_last_modified="2026-10-12T12:53:32+00:00",
                expected_source_sha256="0" * 64)
        content = self.weather.read_text().replace("TUI0000LTCJ", "OTHER")
        self.weather.write_text(content)
        with self.assertRaisesRegex(ValueError, "station identity"):
            self.run_report()

    def test_flagged_weather_is_excluded_and_future_observation_never_joins(self):
        report = self.run_report()
        self.assertEqual(report["weather_quality_exclusions"]["temperature"], 1)
        self.assertEqual(report["population"]["weather_rows_in_range"], 4)
        self.assertEqual(report["population"]["matched_candidate_hours_wind_speed_m_s"], 2)
        self.assertTrue(all(row["weather_observed_at"] is None or
                            row["weather_observed_at"] <= row["observed_hour"]
                            for row in report["candidate_hours"]))
        self.assertEqual(report["descriptive_statistics"]["temperature_c"]["station_mean"],
                         19.667)
        self.assertIsNone(report["descriptive_statistics"]["wind_direction_deg"]["station_mean"])

    def test_published_real_aggregate_is_self_consistent_and_content_addressed(self):
        path = Path(__file__).resolve().parents[1] / "public/data/batman-weather-context-2026-10-11.json"
        report = json.loads(path.read_text())
        digest = report.pop("evidence_sha256")
        canonical = (json.dumps(report, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False) + "\n").encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), digest)
        self.assertEqual(report["population"]["raw_pixels"], 125)
        self.assertEqual(report["population"]["candidate_cell_hours"], 56)
        self.assertEqual(sum(row["candidate_cell_hours"] for row in report["candidate_hours"]), 56)
        self.assertEqual(report["population"]["matched_candidate_hours_temperature_c"], 4)
        self.assertEqual(len(report["source_asset_manifest"]), 10)
        self.assertEqual(len(report["source_receipts"]), 5)
        self.assertTrue(report["thermal_source_provenance"])
        self.assertTrue(all(row["satellite_observation_opportunity"] == "unknown"
                            for row in report["candidate_hours"]))


if __name__ == "__main__":
    unittest.main()
