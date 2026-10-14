"""Source-backed recurrence is descriptive and never a wildfire classifier."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from fire_public.historical_rollup import _bytes
from fire_public.spatial_recurrence import build_spatial_recurrence


FIELDS = ["latitude", "longitude", "bright_ti4", "scan", "track", "acq_date",
          "acq_time", "satellite", "instrument", "confidence", "version",
          "bright_ti5", "frp", "daynight", "type"]
REGIONS = [{"region_id": "ANTALYA_25KM", "latitude": 36.8987, "longitude": 30.8005,
            "radius_km": 25},
           {"region_id": "DALAMAN_25KM", "latitude": 36.7131, "longitude": 28.7925,
            "radius_km": 25}]


class SpatialRecurrenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        def record(lat, lon, date, minute, satellite, confidence="n", daynight="D"):
            return {"latitude": lat, "longitude": lon, "bright_ti4": 320,
                    "scan": .4, "track": .4, "acq_date": date, "acq_time": minute,
                    "satellite": satellite, "instrument": "VIIRS", "confidence": confidence,
                    "version": "2", "bright_ti5": 280, "frp": 2.5,
                    "daynight": daynight, "type": "0"}
        rows = {
            "viirs-jpss1": [record(36.900,30.800,"2025-01-02","1035","N20"),
                            record(36.901,30.800,"2025-02-03","1120","N20","h","N"),
                            record(36.901,30.800,"2025-02-03","1120","N20","h","N"),
                            record(36.713,28.792,"2025-03-04","1200","N20","l")],
            "viirs-snpp": [record(36.900,30.800,"2025-02-03","1212","N"),
                           record(36.713,28.792,"2025-03-04","1300","N","n","N")]
        }
        assets = []
        for family, contents in rows.items():
            filename = f"{family}_2025_Turkey.csv"
            with (self.root / filename).open("w", newline="") as handle:
                writer = csv.DictWriter(handle, FIELDS)
                writer.writeheader(); writer.writerows(contents)
            data = (self.root / filename).read_bytes()
            assets.append({"filename": filename, "year": 2025,
                           "provider": "VIIRS_NOAA20_STANDARD" if family == "viirs-jpss1" else "VIIRS_SNPP_STANDARD",
                           "source_url": f"https://firms.modaps.eosdis.nasa.gov/data/country/{family}/2025/{filename}",
                           "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data),
                           "source_last_modified": "2026-10-10T13:00:00+00:00"})
        self.manifest = {"schema_version": 1, "country_file_label": "Turkey",
                         "region": REGIONS[0], "station": {"id":"TUI0000LTAI", "name":"ANTALYA",
                         "latitude":36.8987,"longitude":30.8005,"elevation_m":53.9,
                         "region_id":"ANTALYA_25KM"},
                         "verified_at":"2026-10-14T15:00:00+00:00",
                         "thermal_assets": assets,
                         "weather_assets": [{"year":2025,"provider":"GHCNh",
                         "source_url":"https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2025/psv/GHCNh_TUI0000LTAI_2025.psv"}]}

    def test_recurrence_and_same_day_sensor_agreement_do_not_classify_fire(self):
        report = build_spatial_recurrence(self.manifest, REGIONS, self.root)
        self.assertEqual(report["population"]["country_source_rows"], 6)
        self.assertEqual(report["population"]["duplicate_source_rows"], 1)
        self.assertEqual(report["population"]["selected_raw_pixels"], 5)
        antalya, dalaman = report["regions"]
        self.assertEqual(antalya["selected_raw_pixels"], 3)
        self.assertEqual(antalya["occupied_bins"], 1)
        self.assertEqual(antalya["recurrently_observed_bins"], 1)
        self.assertEqual(antalya["yearly_quality_rows"][0]["raw_pixels"],3)
        self.assertEqual(antalya["yearly_quality_rows"][0]["source_type_counts"],{"0":3})
        cell = antalya["published_bins"][0]
        self.assertEqual(cell["distinct_dates"], 2)
        self.assertEqual(cell["sensor_agreement_dates"], 1)
        self.assertEqual(cell["confidence_counts"], {"h":1,"n":2})
        self.assertEqual(cell["provider_counts"],
                         {"VIIRS_NOAA20_STANDARD":2,"VIIRS_SNPP_STANDARD":1})
        self.assertEqual(cell["daynight_counts"], {"D":2,"N":1})
        self.assertEqual(cell["classification"], "recurrently_observed_candidate")
        self.assertEqual(cell["source_identity_status"], "unresolved")
        self.assertEqual(dalaman["recurrently_observed_bins"], 0)
        self.assertEqual(dalaman["published_bins"][0]["sensor_agreement_dates"], 1)
        self.assertFalse(report["independent_static_source_evidence"])
        self.assertFalse(report["independent_fire_outcome_valid"])
        self.assertEqual(report, build_spatial_recurrence(self.manifest, REGIONS, self.root))

    def test_source_tamper_and_overlap_fail_closed(self):
        data = json.loads(json.dumps(self.manifest))
        data["thermal_assets"][0]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            build_spatial_recurrence(data, REGIONS, self.root)
        overlap = [REGIONS[0], {**REGIONS[1], "latitude":36.899,"longitude":30.801}]
        with self.assertRaisesRegex(ValueError, "overlap"):
            build_spatial_recurrence(self.manifest, overlap, self.root)

    def test_published_report_is_content_addressed_and_conserves_two_regions(self):
        root = Path(__file__).resolve().parents[1]
        report = json.loads((root / "public/data/turkey-spatial-recurrence-2023-2025.json").read_text())
        digest = report.pop("evidence_sha256")
        self.assertEqual(hashlib.sha256(_bytes(report)).hexdigest(), digest)
        self.assertEqual(report["population"]["selected_raw_pixels"], 1419)
        self.assertEqual(sum(item["selected_raw_pixels"] for item in report["regions"]), 1419)
        self.assertFalse(report["observation_opportunity_verified"])
        antalya = report["regions"][0]
        self.assertGreaterEqual(antalya["potential_static_source_bins"], 1)
        self.assertEqual(antalya["published_bins"][0]["classification"],
                         "potential_static_thermal_source")
        self.assertFalse(antalya["published_bins"][0]["independently_classified"])


if __name__ == "__main__": unittest.main()
