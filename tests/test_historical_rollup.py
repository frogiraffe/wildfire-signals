"""Incremental SQLite analytics contracts using fixtures, never fire labels."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from fire_public.collect import FIRMS_SOURCES
from fire_public.pixel_history import import_release_assets
from fire_public.historical_rollup import build_rollup, query_rollup
from test_pixel_history import make_release, pixel

AT = datetime(2026, 10, 10, tzinfo=timezone.utc)
REGIONS = [
    {"region_id":"A1", "latitude":0, "longitude":0, "radius_km":50},
    {"region_id":"B1", "latitude":0, "longitude":20, "radius_km":50},
]


class HistoricalRollupTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.db=self.root/"pixels.sqlite3"
        for i in range(5):
            when=AT+timedelta(hours=6*i)
            rows=[pixel(FIRMS_SOURCES[0],when=when-timedelta(minutes=20),
                        latitude=.01,longitude=.01,ident=f"a{i}"),
                  pixel(FIRMS_SOURCES[1],when=when-timedelta(minutes=15),
                        latitude=.02,longitude=20.02,ident=f"b{i}")]
            if i==1:
                rows.append(pixel(FIRMS_SOURCES[1],when=AT-timedelta(minutes=20),
                                  latitude=.019,longitude=.019,ident="late-other-sensor"))
            make_release(self.root/f"scan{i}",when,rows)
        import_release_assets(self.db,self.root)

    def test_checkpoints_resume_idempotently_and_query_date_range_without_zero_fill(self):
        first=build_rollup(self.db,REGIONS,max_scans=2)
        self.assertEqual(first["newly_processed_scans"],2)
        with self.assertRaisesRegex(ValueError,"building"):
            query_rollup(self.db,REGIONS,start_date="2026-10-09",end_date="2026-10-11")
        later=build_rollup(self.db,REGIONS)
        self.assertEqual(later["newly_processed_scans"],3)
        self.assertEqual(build_rollup(self.db,list(reversed(REGIONS)))["newly_processed_scans"],0)
        result=query_rollup(self.db,REGIONS,start_date="2026-10-09",end_date="2026-10-11")
        self.assertEqual(result["population"]["selected_raw_pixels"],11)
        self.assertEqual(result["population"]["distinct_candidate_cell_hours"],10)
        self.assertEqual(len(result["source_receipts"]),5)
        self.assertEqual(len(result["source_asset_manifest"]),10)
        self.assertTrue(result["source_provenance"])
        self.assertTrue(all(row["archive_period_complete"] is False for row in result["daily_rows"]))
        self.assertFalse(result["satellite_opportunity_verified"])
        empty=query_rollup(self.db,REGIONS,start_date="2026-11-01",end_date="2026-11-02")
        self.assertEqual(empty["daily_rows"],[])
        self.assertIsNone(empty["verified_fire_count"])
        self.assertEqual(result,query_rollup(self.db,list(reversed(REGIONS)),
                                             start_date="2026-10-09",end_date="2026-10-11"))

    def test_atomic_scan_failure_rolls_back_and_recovers(self):
        build_rollup(self.db,REGIONS,max_scans=1)
        with sqlite3.connect(self.db) as db:
            db.execute("""CREATE TRIGGER fail_rollup BEFORE INSERT ON analytics_region_pixels
                        BEGIN SELECT RAISE(ABORT,'intentional test interruption'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            build_rollup(self.db,REGIONS)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM analytics_processed_scans").fetchone()[0],1)
            db.execute("DROP TRIGGER fail_rollup")
        self.assertEqual(build_rollup(self.db,REGIONS)["newly_processed_scans"],4)

    def test_retroactive_first_capture_change_requires_explicit_rebuild(self):
        build_rollup(self.db,REGIONS)
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE pixel_observations SET first_scan_at=? WHERE source_record_id=(SELECT source_record_id FROM pixel_observations WHERE first_scan_at=? LIMIT 1)",
                       ((AT+timedelta(hours=6)).isoformat(),AT.isoformat()))
        with self.assertRaisesRegex(ValueError,"rebuild"):
            build_rollup(self.db,REGIONS)
        self.assertEqual(build_rollup(self.db,REGIONS,rebuild=True)["newly_processed_scans"],5)

    def test_hourly_query_keeps_original_observation_and_capture_provenance(self):
        build_rollup(self.db,REGIONS)
        result=query_rollup(self.db,REGIONS,start_date="2026-10-09",end_date="2026-10-11",
                            resolution="hour",region_ids=["A1"])
        self.assertEqual(result["population"]["selected_raw_pixels"],6)
        self.assertEqual(result["population"]["distinct_candidate_cell_hours"],5)
        self.assertTrue(all(row["first_captured_at"] and row["first_observed_at"]
                            for row in result["hourly_rows"]))
        self.assertTrue(all(row["region_id"]=="A1" for row in result["hourly_rows"]))
        self.assertIn("VIIRS_NOAA20_NRT",result["provider_raw_pixels"])


if __name__ == "__main__": unittest.main()
