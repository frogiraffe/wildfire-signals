"""Annual country CSVs remain source records, not verified non-detection exposure."""
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fire_public.annual_country_analytics import build_annual_study
from fire_public.historical_rollup import _bytes


REGION = {"region_id": "ANTALYA_25KM", "latitude": 36.8987,
          "longitude": 30.8005, "radius_km": 25}
STATION = {"id": "TUI0000LTAI", "name": "ANTALYA", "latitude": 36.8987,
           "longitude": 30.8005, "elevation_m": 53.9, "region_id": "ANTALYA_25KM"}
PIXEL_FIELDS = ["latitude", "longitude", "bright_ti4", "scan", "track", "acq_date",
                "acq_time", "satellite", "instrument", "confidence", "version",
                "bright_ti5", "frp", "daynight", "type"]
WEATHER_FIELDS = ["STATION", "Station_name", "DATE", "LATITUDE", "LONGITUDE", "ELEVATION",
                  "temperature", "temperature_Source_Code", "temperature_Quality_Code",
                  "wind_speed", "wind_speed_Source_Code", "wind_speed_Quality_Code",
                  "wind_direction", "wind_direction_Source_Code", "wind_direction_Quality_Code",
                  "wind_direction_Measurement_Code", "relative_humidity",
                  "relative_humidity_Quality_Code"]


class AnnualCountryAnalyticsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        sources = []
        for provider, satellite in (("VIIRS_NOAA20_STANDARD", "N20"),
                                    ("VIIRS_SNPP_STANDARD", "N")):
            name = f"{provider}.csv"
            with (self.root / name).open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=PIXEL_FIELDS)
                writer.writeheader()
                def row(day, minute, latitude):
                    return {"latitude": latitude, "longitude": 30.8,
                            "bright_ti4": 320, "scan": .4, "track": .4,
                            "acq_date": day, "acq_time": minute,
                            "satellite": satellite, "instrument": "VIIRS",
                            "confidence": "n", "version": "2", "bright_ti5": 280,
                            "frp": 2.5, "daynight": "D", "type": "0"}
                writer.writerow(row("2025-01-02", "1035", 36.9))
                writer.writerow(row("2025-01-02", "1035", 36.9))  # exact source duplicate
                writer.writerow(row("2025-02-02", "1035", 10.0))  # outside pilot
            sources.append(self.asset(name, f"https://firms.modaps.eosdis.nasa.gov/data/country/"
                                      f"{'viirs-jpss1' if satellite == 'N20' else 'viirs-snpp'}/2025/"
                                      f"{'viirs-jpss1' if satellite == 'N20' else 'viirs-snpp'}_2025_Turkey.csv",
                                      provider, 2025))
        weather_name = "station.psv"
        with (self.root / weather_name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=WEATHER_FIELDS, delimiter="|")
            writer.writeheader()
            for time, value in (("2025-01-02T10:20:00", "20"),
                                ("2025-01-02T11:00:00", "25")):
                writer.writerow({"STATION": "TUI0000LTAI", "Station_name": "ANTALYA",
                                 "DATE": time, "LATITUDE": 36.8987, "LONGITUDE": 30.8005,
                                 "ELEVATION": 53.9, "temperature": value,
                                 "temperature_Source_Code": "223", "temperature_Quality_Code": "1",
                                 "wind_speed": "3", "wind_speed_Source_Code": "223",
                                 "wind_speed_Quality_Code": "1", "wind_direction": "999",
                                 "wind_direction_Source_Code": "223",
                                 "wind_direction_Measurement_Code": "V",
                                 "relative_humidity": "60"})
        self.manifest = {"schema_version": 1, "country_file_label": "Turkey",
                         "region": REGION, "station": STATION,
                         "verified_at": "2026-10-14T15:00:00+00:00",
                         "thermal_assets": sources,
                         "weather_assets": [self.asset(weather_name,
                             "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/"
                             "hourly/access/by-year/2025/psv/GHCNh_TUI0000LTAI_2025.psv",
                             "GHCNh", 2025)]}

    def asset(self, name, url, provider, year):
        data = (self.root / name).read_bytes()
        return {"filename": name, "source_url": url, "provider": provider,
                "year": year, "size_bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "source_last_modified": "2026-10-10T13:52:47+00:00"}

    def test_real_grain_positive_only_and_prior_weather_join(self):
        report = build_annual_study(self.manifest, self.root)
        self.assertEqual(report["population"]["country_source_rows"], 6)
        self.assertEqual(report["population"]["duplicate_source_rows"], 2)
        self.assertEqual(report["population"]["selected_raw_pixels"], 2)
        self.assertEqual(len(report["daily_rows"]), 2)
        self.assertEqual(report["daily_rows"][0]["observed_date"], "2025-01-02")
        self.assertEqual(report["population"]["candidate_provider_hours"], 2)
        self.assertEqual(report["population"]["weather_matched_provider_hours_temperature_c"], 2)
        self.assertEqual(report["candidate_provider_hours"][0]["temperature_c"], 20.0)
        self.assertEqual(report["candidate_provider_hours"][0]["weather_observed_at"],
                         "2025-01-02T10:20:00+00:00")
        self.assertEqual(report["monthly_rows"][0]["observed_month"], "2025-01")
        self.assertFalse(report["observation_opportunity_verified"])
        self.assertIsNone(report["no_detection_count"])
        self.assertEqual(report, build_annual_study(self.manifest, self.root))

    def test_integrity_and_source_contract_fail_closed(self):
        asset = self.manifest["thermal_assets"][0]
        data = json.loads(json.dumps(self.manifest))
        data["thermal_assets"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_annual_study(data, self.root)
        data = json.loads(json.dumps(self.manifest))
        data["thermal_assets"][0]["source_url"] = "https://example.com/not-a-source.csv"
        with self.assertRaisesRegex(ValueError, "source URL"):
            build_annual_study(data, self.root)
        path = self.root / asset["filename"]
        path.write_bytes(path.read_bytes().replace(b"2025-01-02", b"2026-01-02"))
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_annual_study(self.manifest, self.root)

    def test_missing_prior_weather_stays_missing_and_malformed_year_rejected(self):
        data = json.loads(json.dumps(self.manifest))
        data["thermal_assets"][0]["year"] = "2025"
        with self.assertRaisesRegex(ValueError, "integers"):
            build_annual_study(data, self.root)
        path = self.root / "station.psv"
        text = path.read_text().replace("2025-01-02T10:20:00", "2025-01-02T11:20:00")
        path.write_text(text)
        data = json.loads(json.dumps(self.manifest))
        data["weather_assets"][0]["size_bytes"] = path.stat().st_size
        data["weather_assets"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "unordered"):
            build_annual_study(data, self.root)
        path.write_text(text.replace("2025-01-02T11:00:00", "2025-01-02T12:00:00"))
        data["weather_assets"][0]["size_bytes"] = path.stat().st_size
        data["weather_assets"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        report = build_annual_study(data, self.root)
        self.assertEqual(report["population"]["candidate_provider_hours"], 2)
        self.assertNotIn("weather_matched_provider_hours_temperature_c", report["population"])
        self.assertTrue(all(row["temperature_c"] is None for row in report["candidate_provider_hours"]))

    def test_published_real_report_content_address_and_denominators(self):
        root = Path(__file__).resolve().parents[1]
        report = json.loads((root / "public/data/antalya-annual-context-2023-2025.json").read_text())
        evidence = report.pop("evidence_sha256")
        self.assertEqual(hashlib.sha256(_bytes(report)).hexdigest(), evidence)
        self.assertEqual(report["population"]["source_files"], 6)
        self.assertEqual(report["population"]["weather_files"], 3)
        self.assertFalse(report["observation_opportunity_verified"])
        self.assertIsNone(report["no_detection_count"])


if __name__ == "__main__": unittest.main()
