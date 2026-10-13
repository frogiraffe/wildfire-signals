"""Source-receipt integration and numerical contracts; fixtures are not fire labels."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from fire_public.collect import FIRMS_SOURCES
from fire_public.pixel_history import import_release_assets
from fire_public.thermal_capture_analytics import build_capture_pilot, evaluate_capture_model
from test_pixel_history import make_release, pixel

FIRST=datetime(2026,10,12,0,tzinfo=timezone.utc)
REGIONS=[{"region_id":f"R{i}","latitude":0,"longitude":i*12,
          "radius_km":100} for i in range(6)]


class ThermalCaptureAnalyticsTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.db=self.root/"pixels.sqlite3"

    def populate(self, *, failed_scan=None, cross_scan_duplicate=False):
        for scan_index in range(5):
            at=FIRST+timedelta(hours=6*scan_index)
            rows=[]
            for region_index in range(6):
                # One distinct cell-hour per region/scan. Scan zero is a warmup.
                rows.append(pixel(FIRMS_SOURCES[0],when=at-timedelta(minutes=30),
                    latitude=.011,longitude=region_index*12+.011,
                    ident=f"{scan_index}-{region_index}"))
            if scan_index==1:
                # Same cell/hour from a second sensor counts as one candidate.
                rows.append(pixel(FIRMS_SOURCES[1],when=at-timedelta(minutes=25),
                    latitude=.019,longitude=.019,ident="second-sensor"))
                if cross_scan_duplicate:
                    rows.append(pixel(FIRMS_SOURCES[1],when=FIRST-timedelta(minutes=25),
                        latitude=.019,longitude=.019,ident="late-second-sensor"))
            states={source:"complete" for source in FIRMS_SOURCES}
            if scan_index==failed_scan:states[FIRMS_SOURCES[1]]="failed"
            make_release(self.root/f"scan-{scan_index}",at,rows,states=states)
        import_release_assets(self.db,self.root)

    def test_verified_pixels_become_scan_and_daily_rows_without_fire_labels(self):
        self.populate()
        result=build_capture_pilot(self.db,REGIONS,heldout_region_ids=["R4","R5"])
        self.assertEqual(result["input_population"]["verified_scan_receipts"],5)
        self.assertEqual(result["input_population"]["unique_raw_pixels"],31)
        self.assertEqual(result["input_population"]["selected_region_raw_pixels"],31)
        self.assertEqual(len(result["scan_rows"]),30)
        first=next(row for row in result["scan_rows"]
                   if row["region_id"]=="R0" and row["scan_index"]==1)
        self.assertEqual(first["new_raw_pixels"],2)
        self.assertEqual(first["new_candidate_cell_hours"],1)
        self.assertEqual(first["sensor_raw_pixels"][FIRMS_SOURCES[1]],1)
        self.assertFalse(result["satellite_opportunity_verified"])
        self.assertIsNone(result["verified_fire_count"])
        self.assertEqual(result,build_capture_pilot(self.db,list(reversed(REGIONS)),
                                               heldout_region_ids=["R5","R4"]))
        self.assertTrue(all(row["archive_period_complete"] is False
                            for row in result["daily_rows"]+result["weekly_rows"]+
                            result["monthly_rows"]))

    def test_model_uses_prior_scan_only_and_separates_time_and_geography(self):
        self.populate()
        result=build_capture_pilot(self.db,REGIONS,heldout_region_ids=["R4","R5"])
        model=result["model_research"]
        self.assertEqual(model["status"],"experimental")
        self.assertEqual(model["target"],"next_scan_new_candidate_cell_hours")
        self.assertEqual(model["splits"]["train"]["n"],8)
        self.assertEqual(model["splits"]["temporal_holdout"]["n"],4)
        self.assertEqual(model["splits"]["geographic_holdout"]["n"],4)
        self.assertEqual(model["splits"]["joint_holdout"]["n"],2)
        self.assertEqual(model["splits"]["joint_holdout"]["persistence_mae"],0)
        self.assertIsNone(model["wildfire_prediction_skill"])
        self.assertLess(model["training_last_target_scan_at"],
                        model["first_temporal_holdout_target_scan_at"])

    def test_later_sensor_of_same_cell_hour_does_not_create_second_candidate(self):
        self.populate(cross_scan_duplicate=True)
        result=build_capture_pilot(self.db,REGIONS,heldout_region_ids=["R4","R5"])
        later=next(row for row in result["scan_rows"]
                   if row["region_id"]=="R0" and row["scan_index"]==1)
        self.assertEqual(later["new_raw_pixels"],3)
        self.assertEqual(later["new_candidate_cell_hours"],1)
        self.assertEqual(sum(row["new_candidate_cell_hours"] for row in result["scan_rows"]),
                         sum(row["new_candidate_cell_hours"] for row in result["daily_rows"]))

    def test_failed_source_receipt_withholds_model_instead_of_treating_zero_as_outcome(self):
        self.populate(failed_scan=2)
        result=build_capture_pilot(self.db,REGIONS,heldout_region_ids=["R4","R5"])
        self.assertEqual(result["model_research"]["status"],"withheld")
        self.assertIn("complete",result["model_research"]["reason"])
        self.assertEqual(result["source_receipts"][2]["source_states"][FIRMS_SOURCES[1]],"failed")

    def test_numerical_model_does_not_use_future_targets_for_fit(self):
        scans=[{"scan_at":(FIRST+timedelta(hours=6*i)).isoformat(),
                "captured_at":(FIRST+timedelta(hours=6*i,minutes=5)).isoformat(),
                "source_states":{key:"complete" for key in FIRMS_SOURCES}}
               for i in range(5)]
        rows=[{"scan_index":i,"region_id":r["region_id"],
               "new_candidate_cell_hours":i+j} for i in range(5)
              for j,r in enumerate(REGIONS)]
        original=evaluate_capture_model(rows,scans,["R4","R5"])
        changed=[dict(row,new_candidate_cell_hours=10000)
                 if row["scan_index"]==4 else row for row in rows]
        later=evaluate_capture_model(changed,scans,["R4","R5"])
        self.assertEqual(original["coefficients"],later["coefficients"])
        self.assertEqual(original["splits"]["train"],later["splits"]["train"])
        self.assertNotEqual(original["splits"]["temporal_holdout"],
                            later["splits"]["temporal_holdout"])

    def test_rejects_missing_or_unsafe_input_without_writing(self):
        with self.assertRaises(FileNotFoundError):
            build_capture_pilot(self.root/"absent.sqlite3",REGIONS,
                                heldout_region_ids=["R4","R5"])
        self.populate()
        with self.assertRaises(ValueError):
            build_capture_pilot(self.db,REGIONS,
                                heldout_region_ids=["unknown"])
        with self.assertRaises(ValueError):
            build_capture_pilot(self.db,REGIONS+[REGIONS[0]],
                                heldout_region_ids=["R4","R5"])

    def test_committed_real_aggregate_is_content_addressed_and_population_balances(self):
        artifact=Path(__file__).resolve().parents[1]/"public/data/thermal-capture-pilot-2026-10-13.json"
        doc=json.loads(artifact.read_text())
        digest=doc.pop("evidence_sha256")
        canonical=(json.dumps(doc,sort_keys=True,separators=(",",":"),
                              ensure_ascii=False,allow_nan=False)+"\n").encode()
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),digest)
        population=doc["input_population"]
        self.assertEqual(population["unique_raw_pixels"],
                         population["selected_region_raw_pixels"]+
                         population["outside_selected_regions_raw_pixels"])
        self.assertEqual(sum(row["new_raw_pixels"] for row in doc["scan_rows"]),
                         population["selected_region_raw_pixels"])
        self.assertEqual(sum(row["new_candidate_cell_hours"] for row in doc["scan_rows"]),
                         sum(row["new_candidate_cell_hours"] for row in doc["daily_rows"]))
        self.assertFalse(doc["model_research"]["model_comparison_supported"])


if __name__=="__main__":unittest.main()
