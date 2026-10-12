"""Provider-shaped synthetic fixtures test real multi-year SQLite and GeoJSON path.

No numerical outcomes in these tests are scientific fire-occurrence estimates.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fire_public.official_perimeters import sync_year
from fire_public.perimeter_study import (
    run_study, study_report, validate_years, _canonical,
)

CAPTURE = "2026-10-13T13:17:00Z"
IDS = [9, 37, 12, 45, 800, 1002, 732, 409, 1973, 534, 993, 21]


def item(oid, year):
    center = -125 + (oid % 20) / 10
    return {
        "type": "Feature",
        "properties": {
            "OBJECTID": oid,
            "GlobalID": f"{{source-{year}-{oid}}}",
            "FIRE_YEAR_INT": year,
            "INCIDENT": f"Archived example {year}/{oid}",
            "GIS_ACRES": float(oid % 100 + 1),
            "SOURCE": "USFS",
        },
        "geometry": {"type": "Polygon", "coordinates": [[
            [center, 35], [center + 0.01, 35],
            [center + 0.01, 35.01], [center, 35.01], [center, 35],
        ]]},
    }


class FakeNifc:
    def __init__(self):
        self.calls = []
        self.corrupt_year = None

    def __call__(self, params):
        self.calls.append(dict(params))
        if "where" in params:
            year = int(params["where"].split("=")[-1].strip())
            return {"objectIds": list(reversed(IDS))}
        object_ids = [int(x) for x in params["objectIds"].split(",")]
        # Identify the year from an internal test attribute set by helper.
        year = self.current_year
        features = [item(oid, year) for oid in object_ids]
        if self.corrupt_year == year:
            features[-1]["properties"]["FIRE_YEAR_INT"] = year - 1
        return {"type": "FeatureCollection", "features": features}


class SampledStudyTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.db = self.root / "sample.sqlite3"
        self.fake = FakeNifc()

    def provider(self, args):
        if "where" in args:
            self.fake.current_year = int(args["where"].split("=")[-1].strip())
        return self.fake(args)

    def sample(self, **kwargs):
        return run_study(
            self.db, years=[2017, 2018], records_per_year=4,
            get_json=self.provider, clock=lambda: CAPTURE, **kwargs)

    def test_two_year_study_source_counts_and_original_geojson(self):
        r, features = self.sample(seed="unit-test-v1")
        self.assertEqual(r["requested_fire_years"], [2017, 2018])
        self.assertEqual(r["stored_polygon_records"], 8)
        self.assertTrue(r["complete_requested_year_sample"])
        self.assertFalse(r["source_fire_occurrence_coverage_complete"])
        self.assertEqual(r["negative_labels_created"], 0)
        self.assertFalse(r["model_ready"])
        self.assertEqual([y["sampled_polygons"] for y in r["year_results"]], [4, 4])
        self.assertEqual([y["source_object_ids"] for y in r["year_results"]], [12, 12])
        self.assertTrue(all(y["partial_source_record_sample"] for y in r["year_results"]))
        self.assertEqual(features["type"], "FeatureCollection")
        self.assertEqual(len(features["features"]), 8)
        self.assertTrue(all(x["geometry"]["type"] == "Polygon" for x in features["features"]))
        self.assertTrue(all(x["properties"]["SOURCE"] == "USFS" for x in features["features"]))
        self.assertEqual(len(self.fake.calls), 4)  # two ID queries + two GeoJSON queries
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM perimeter_fetches").fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM perimeter_sample_metadata").fetchone()[0], 2)

    def test_hash_sampling_is_deterministic_and_not_first_ids(self):
        study, feature_collection = self.sample(seed="a-study-seed")
        first = [x["properties"]["OBJECTID"] for x in feature_collection["features"]
                 if x["properties"]["FIRE_YEAR_INT"] == 2018]
        self.assertNotEqual(first, sorted(IDS)[:4])
        again, second_collection = self.sample(seed="a-study-seed")
        second = [x["properties"]["OBJECTID"] for x in second_collection["features"]
                  if x["properties"]["FIRE_YEAR_INT"] == 2018]
        self.assertEqual(first, second)
        self.assertEqual(again["stored_polygon_records"], 8)
        new_seed, changed = self.sample(seed="another-seed")
        third = [x["properties"]["OBJECTID"] for x in changed["features"]
                 if x["properties"]["FIRE_YEAR_INT"] == 2018]
        self.assertNotEqual(third, first)
        self.assertTrue(new_seed["complete_requested_year_sample"])

    def test_standard_old_first_id_mode_remains_supported(self):
        r = sync_year(self.db, year=2018, max_records=3,
                      get_json=self.provider, clock=lambda:CAPTURE)
        self.assertEqual(r["selection_mode"], "first")
        self.assertEqual(r["fetched_perimeters"], 3)
        with sqlite3.connect(self.db) as db:
            stored = db.execute("""
                SELECT object_id FROM perimeter_versions ORDER BY object_id
            """).fetchall()
            self.assertEqual([x[0] for x in stored], sorted(IDS)[:3])

    def test_incomplete_year_at_cutoff_remains_unknown_not_zero_fires(self):
        self.sample()
        prior, previous_geo = study_report(
            self.db, years=[2017, 2018], at="2018-10-01T00:00:00Z")
        self.assertEqual(prior["stored_polygon_records"], 0)
        self.assertFalse(prior["complete_requested_year_sample"])
        self.assertEqual(previous_geo["features"], [])
        self.assertEqual(prior["year_results"][0]["archive_status"],
                         "not_captured_by_decision")
        self.assertIsNone(prior["year_results"][0]["source_object_ids"])

    def test_record_digest_detects_geometry_corruption(self):
        self.sample()
        with sqlite3.connect(self.db) as db:
            db.execute("""UPDATE perimeter_versions
                SET attributes_json='{"OBJECTID":999}'
                WHERE object_id=(SELECT MIN(object_id) FROM perimeter_versions)""")
        with self.assertRaisesRegex(ValueError, "identity changed|SHA-256 mismatch"):
            study_report(self.db, at=CAPTURE, years=[2017, 2018])

    def test_missing_records_fail_archive_verification(self):
        self.sample()
        with sqlite3.connect(self.db) as db:
            db.execute("""DELETE FROM perimeter_versions
                WHERE rowid=(SELECT MIN(rowid) FROM perimeter_versions)""")
        with self.assertRaisesRegex(ValueError, "row count contradicts"):
            study_report(self.db, at=CAPTURE, years=[2017, 2018])

    def test_page_failure_does_not_generate_fake_complete_study(self):
        self.fake.corrupt_year = 2018
        with self.assertRaisesRegex(ValueError, "year mismatch"):
            self.sample()
        with sqlite3.connect(self.db) as db:
            # A previous valid 2017 capture may remain; this is deliberate and documented.
            self.assertEqual(db.execute("SELECT COUNT(*) FROM perimeter_fetches").fetchone()[0], 1)
        study, geo = study_report(self.db, at=CAPTURE, years=[2017, 2018])
        self.assertFalse(study["complete_requested_year_sample"])
        self.assertEqual(study["stored_polygon_records"], 4)
        self.assertEqual(study["year_results"][1]["archive_status"], "not_captured_by_decision")

    def test_validation_budgets_and_bad_seed(self):
        for years in ([], [2019, 2019], [1899], [2020], list(range(2000, 2009))):
            with self.subTest(years=years), self.assertRaises(ValueError):
                validate_years(years)
        for count in (0, 31, True):
            with self.assertRaises(ValueError):
                run_study(self.db,years=[2018],records_per_year=count,
                          get_json=self.provider)
        with self.assertRaises(ValueError):
            run_study(self.db,years=[2018],records_per_year=2,
                      seed="🙂",get_json=self.provider)

    def test_cli_offline_report_geojson_and_output_protection(self):
        self.sample()
        report_path = self.root / "study.json"
        geo_path = self.root / "sample.geojson"
        cmd = [sys.executable, "-m", "fire_public.perimeter_study", "report",
               "--db", str(self.db), "--year", "2018", "--year", "2017",
               "--at", CAPTURE,
               "--report", str(report_path), "--geojson", str(geo_path)]
        complete = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(complete.returncode, 0, complete.stderr)
        self.assertEqual(json.loads(report_path.read_text())["stored_polygon_records"], 8)
        self.assertEqual(len(json.loads(geo_path.read_text())["features"]), 8)
        again = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)
        destructive = cmd[:]
        destructive[destructive.index("--report") + 1] = str(self.db)
        self.assertNotEqual(subprocess.run(destructive,capture_output=True).returncode,0)


if __name__ == "__main__":
    unittest.main()
