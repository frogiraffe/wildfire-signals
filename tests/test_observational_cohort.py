"""Research cohort v3: original-pixel sources -> as-of unlabeled study samples.

Fixtures are synthetic, emitted through the existing verified PixelArchive
receipt/import contract. No fixture is empirical wildfire ground truth.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from fire_public.collect import FIRMS_SOURCES
from fire_public.pixel_history import import_release_assets
from fire_public.observational_cohort import (
    build_observational_cohort,validate_regions,export_cohort,render_quality_html
)
from test_pixel_history import pixel,make_release

FIRST=datetime(2026,10,12,0,0,tzinfo=timezone.utc)
A={"region_id":"ANTALYA","latitude":0,"longitude":10,"radius_km":100}
B={"region_id":"DISTANT_AREA","latitude":0,"longitude":100,"radius_km":100}


class ObservationalCohortTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.assets=self.root/"release-assets"
        self.db=self.root/"verified-pixels.sqlite3"

    def original(self,i,j=0,source=FIRMS_SOURCES[0],lon=10.01,when=None):
        at=when or FIRST+timedelta(hours=i*2,minutes=30)
        return pixel(source,when=at,latitude=0.012,
                     longitude=lon,ident=f"receipt-{i}-{j}-{source}")

    def fill(self,failed_at=None,with_late=False):
        for i in range(14 if with_late else 13):
            scan=FIRST+timedelta(hours=2*i+1)
            states={x:"complete" for x in FIRMS_SOURCES}
            if i==failed_at:
                states[FIRMS_SOURCES[0]]="failed"
            readings=[self.original(i,source=FIRMS_SOURCES[1] if i==failed_at else FIRMS_SOURCES[0])]
            if with_late and i==12:
                readings.append(self.original(12,1,source=FIRMS_SOURCES[1],
                                              when=FIRST+timedelta(hours=4,minutes=30)))
            make_release(self.assets/f"scan-{i:02d}",scan,readings,states=states)
        imported=import_release_assets(self.db,self.assets)
        self.assertEqual(imported["imported_scans"],14 if with_late else 13)

    def cohort(self,regions=None,**options):
        params={
          "start_at":(FIRST+timedelta(hours=24)).isoformat(),
          "end_at":(FIRST+timedelta(hours=25)).isoformat(),
          "cadence_hours":1,"lookback_hours":24,"target_hours":24,
        }
        params.update(options)
        return build_observational_cohort(self.db,regions or [A,B],**params)

    def test_complete_genuine_pixel_receipts_yield_source_audited_unlabeled_rows(self):
        self.fill()
        cohort=self.cohort()
        self.assertEqual(len(cohort["rows"]),2)
        frame=cohort["manifest"]
        self.assertEqual(frame["counts"]["collector_request_audited_rows"],2)
        self.assertEqual(frame["counts"]["censored_source_rows"],0)
        self.assertEqual(frame["counts"]["model_trainable_rows"],0)
        self.assertEqual(frame["counts"]["independently_labeled_negative_rows"],0)
        self.assertFalse(frame["no_satellite_acquisition_denominator"] is False)
        one,two=cohort["rows"]
        self.assertEqual(one["region_id"],"ANTALYA")
        self.assertEqual(one["source_completed_bins"],12)
        self.assertEqual(one["observed_archive_subset"]["candidate_cell_hours"],12)
        self.assertEqual(one["features"]["candidate_cell_hours"],12)
        self.assertEqual(one["features"]["unique_raw_pixels"],12)
        self.assertEqual(one["features"]["theil_sen_cell_hours_per_hour"],0)
        self.assertEqual(one["features"]["later_minus_earlier_cell_hours"],0)
        self.assertEqual(one["outcome_window_end_exclusive"],
                         (FIRST+timedelta(hours=48)).isoformat())
        self.assertEqual(one["source_first_captured_no_later_than"],one["decision_at"])
        self.assertEqual(two["observed_archive_subset"]["candidate_cell_hours"],0)
        self.assertEqual(two["features"]["candidate_cell_hours"],0)
        self.assertIsNone(two["target_label"])  # zero thermal rows is NOT negative
        self.assertIsNone(one["target_label"])
        self.assertIsNone(one["target_label_available_at"])
        self.assertIsNone(one["independent_label_source"])
        self.assertFalse(one["model_training_allowed"])
        self.assertFalse(one["orbital_exposure_validated"])
        self.assertFalse(one["region_observation_completeness_validated"])
        self.assertEqual(one["split_assignment"],"unassigned")
        self.assertEqual(one["source_linkage_to_agency_fire"],"not_asserted")
        self.assertNotEqual(one["sample_id"],two["sample_id"])
        self.assertEqual(len(one["source_provenance_receipts_sha256"]),64)
        self.assertEqual(cohort,self.cohort([B,A]))  # input order never affects output

    def test_failed_source_censors_model_features_but_preserves_partial_observation(self):
        self.fill(failed_at=5)
        result=self.cohort([A])
        row=result["rows"][0]
        self.assertEqual(result["manifest"]["counts"]["censored_source_rows"],1)
        self.assertEqual(row["sample_quality"],"censored_by_missing_or_incomplete_source_receipts")
        self.assertEqual(row["source_completed_bins"],11)
        self.assertEqual(row["observed_archive_subset"]["candidate_cell_hours"],12)
        self.assertTrue(all(value is None for value in row["features"].values()))
        self.assertIsNone(row["target_label"])
        # Failing NOAA20 should not censor *separately audited* NOAA21
        only=self.cohort([A],source=FIRMS_SOURCES[1])
        self.assertTrue(only["rows"][0]["collector_only_completeness"])
        self.assertEqual(only["rows"][0]["features"]["candidate_cell_hours"],1)
        self.assertIsNone(only["rows"][0]["target_label"])

    def test_past_decision_cannot_see_late_received_source_observation(self):
        self.fill(with_late=True)
        result=self.cohort([A],start_at=(FIRST+timedelta(hours=24)).isoformat(),
                end_at=(FIRST+timedelta(hours=27)).isoformat())
        by_date={r["decision_at"]:r for r in result["rows"]}
        early=by_date[(FIRST+timedelta(hours=24)).isoformat()]
        late=by_date[(FIRST+timedelta(hours=26)).isoformat()]
        self.assertEqual(early["observed_archive_subset"]["unique_raw_pixels"],12)
        # Old raw pixel first appeared in the scan at hour 25, not at hour 24.
        self.assertEqual(late["observed_archive_subset"]["unique_raw_pixels"],14)
        self.assertNotEqual(early["source_provenance_receipts_sha256"],
                            late["source_provenance_receipts_sha256"])
        self.assertIsNone(late["target_label"])

    def test_empty_and_missed_scan_bin_never_creates_negative_label(self):
        when=FIRST+timedelta(hours=25)
        make_release(self.assets/"sparse",when,[])
        import_release_assets(self.db,self.assets)
        cohort=self.cohort([A])
        row=cohort["rows"][0]
        self.assertEqual(row["source_missing_receipt_bins"],12)
        self.assertEqual(row["observed_archive_subset"]["candidate_cell_hours"],0)
        self.assertIsNone(row["features"]["candidate_cell_hours"])
        self.assertIsNone(row["target_label"])
        self.assertFalse(row["model_training_allowed"])

    def test_overlap_across_dateline_and_duplicate_ids_rejected_pre_labeling(self):
        a={"region_id":"EAST","latitude":0,"longitude":179.9,"radius_km":50}
        b={"region_id":"WEST","latitude":0,"longitude":-179.9,"radius_km":50}
        with self.assertRaisesRegex(ValueError,"overlap"):
            validate_regions([a,b])
        with self.assertRaisesRegex(ValueError,"overlap"):
            validate_regions([A,{**A,"region_id":"ANTALYA2"}])
        with self.assertRaisesRegex(ValueError,"duplicate"):
            validate_regions([A,A])
        with self.assertRaises(ValueError):
            validate_regions([{**A,"latitude":91}])
        with self.assertRaises(ValueError):
            validate_regions([{**A,"longitude":float("nan")}])
        with self.assertRaises(ValueError):
            validate_regions([{"region_id":"<script>","latitude":0,"longitude":0,"radius_km":50}])
        with self.assertRaises(ValueError):
            validate_regions([{**A,"extra":"unreviewed"}])
        self.assertEqual([x["region_id"] for x in validate_regions([B,A])],
                         ["ANTALYA","DISTANT_AREA"])

    def test_schedule_bounds_malformed_dates_sources_and_missing_sqlite(self):
        self.fill()
        issues=[
            {"start_at":"2026-10-13T00:00:00","end_at":"2026-10-13T01:00:00Z"},
            {"start_at":"2026-10-13T00:00:00Z","end_at":"2026-10-13T00:00:00Z"},
            {"start_at":"2026-10-13T00:00:00Z","end_at":"2026-10-13T01:30:00Z"},
            {"cadence_hours":5},{"lookback_hours":6},{"target_hours":0},
            {"source":"nifc_wfigs"},
            {"end_at":"2026-10-14T00:00:00Z"}
        ]
        for opts in issues:
            with self.subTest(opts=opts), self.assertRaises(ValueError):
                self.cohort([A],**opts)
        with self.assertRaisesRegex(ValueError,"256"):
            self.cohort([A,B],end_at=(FIRST+timedelta(hours=24+130)).isoformat(),
                        cadence_hours=1)
        with self.assertRaises(FileNotFoundError):
            build_observational_cohort(self.root/"missing.sqlite3",[A],
                start_at=(FIRST+timedelta(hours=24)).isoformat(),
                end_at=(FIRST+timedelta(hours=25)).isoformat(),cadence_hours=1)

    def test_jsonl_csv_html_exports_are_private_complete_and_new_only(self):
        self.fill()
        cohort=self.cohort([A,B])
        output=self.root/"private-analysis"
        result=export_cohort(cohort,output)
        self.assertEqual(result["rows"],2)
        self.assertEqual(result["label_count"],0)
        self.assertEqual(set(result["files"]),
                        {"manifest.json","observations.jsonl","observations.csv","quality.html"})
        self.assertEqual(output.stat().st_mode & 0o777,0o700)
        for file in output.iterdir():
            self.assertEqual(file.stat().st_mode & 0o777,0o600)
        doc=json.loads((output/"manifest.json").read_text())
        for name,metadata in doc["files"].items():
            self.assertEqual(hashlib.sha256((output/name).read_bytes()).hexdigest(),
                             metadata["sha256"])
        rows=[json.loads(x) for x in (output/"observations.jsonl").read_text().splitlines()]
        self.assertEqual(rows,cohort["rows"])
        with (output/"observations.csv").open(newline="") as stream:
            table=list(csv.DictReader(stream))
        self.assertEqual(len(table),2)
        self.assertEqual(table[0]["candidate_cell_hours"],"12")
        self.assertEqual(table[1]["candidate_cell_hours"],"0")
        self.assertEqual(table[1]["target_label"],"")
        self.assertEqual(table[1]["model_training_allowed"],"False")
        html=(output/"quality.html").read_text()
        self.assertIn("Unlabeled prospective observation study frame",html)
        self.assertIn("ANTALYA",html)
        self.assertNotIn("<script",html)
        self.assertNotIn("https://",html)
        before=(output/"manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError,"new private cohort"):
            export_cohort(cohort,output)
        self.assertEqual((output/"manifest.json").read_bytes(),before)

    def test_cli_end_to_end_with_real_receipt_contract(self):
        self.fill()
        region_file=self.root/"regions.json"
        region_file.write_text(json.dumps([A,B]),encoding="utf-8")
        output=self.root/"cohort-v3"
        cmd=[sys.executable,"-m","fire_public.observational_cohort",
            "--pixel-db",str(self.db),"--regions-json",str(region_file),
            "--start-at",(FIRST+timedelta(hours=24)).isoformat(),
            "--end-at",(FIRST+timedelta(hours=25)).isoformat(),
            "--cadence-hours","1","--lookback-hours","24",
            "--target-hours","24","--output-dir",str(output)]
        result=subprocess.run(cmd,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["rows"],2)
        repeat=subprocess.run(cmd,text=True,capture_output=True)
        self.assertNotEqual(repeat.returncode,0)
        self.assertEqual(len((output/"observations.jsonl").read_text().splitlines()),2)


if __name__=="__main__":
    unittest.main()
