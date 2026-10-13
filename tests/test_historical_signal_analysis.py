"""Historical analysis v2: 12-bin source-state and as-of statistical verification.

All fixtures are synthetic but use the repository's genuine PixelArchive source
receipt/import pathway; test scores are not real wildfire metrics.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from fire_public.collect import FIRMS_SOURCES
from fire_public.pixel_history import import_release_assets
from fire_public.historical_signal_analysis import analyze_historical_signals, render_html
from test_pixel_history import pixel, make_release

START=datetime(2026,10,12,0,0,tzinfo=timezone.utc)
END=START+timedelta(hours=24)


class HistoricalAnalysisTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.assets=self.root/"verified-originals"
        self.db=self.root/"pixel-history.sqlite3"

    def scan(self,i,rows=(),states=None):
        when=START+timedelta(hours=2*i+1)
        return make_release(self.assets/f"scan-{i:02d}",when,list(rows),
                            states=states)

    def observation(self,i,j,*,source=FIRMS_SOURCES[0],lon=None,lat=0):
        observed=START+timedelta(hours=2*i,minutes=30)
        return pixel(source,when=observed,latitude=lat,
                     longitude=10.005+j*.05 if lon is None else lon,
                     ident=f"unique-{i}-{j}-{source}")

    def load_complete(self):
        for i in range(12):
            rows=[self.observation(i,j) for j in range(i)]
            if i>0:
                rows.append(self.observation(i,0,source=FIRMS_SOURCES[1]))
            self.scan(i,rows)
        imported=import_release_assets(self.db,self.assets)
        self.assertEqual(imported["imported_scans"],12)

    def report(self,**params):
        kw=dict(at=END.isoformat(),hours=24,latitude=0,longitude=10,
                radius_km=120,source="all")
        kw.update(params)
        return analyze_historical_signals(self.db,**kw)

    def test_complete_retrospective_source_scans_enable_robust_descriptive_trend(self):
        self.load_complete()
        d=self.report()
        self.assertEqual(d["scan_receipts"],12)
        self.assertEqual(d["bin_quality"]["bins_with_no_receipt"],0)
        self.assertEqual(d["bin_quality"]["bins_with_all_selected_sources_complete_receipts"],12)
        self.assertFalse(d["bin_quality"]["satellite_overpass_opportunities_known"])
        self.assertTrue(d["bin_quality"]["trend_descriptive_only_available"])
        self.assertEqual([b["observed_cell_hours"] for b in d["bins"]],list(range(12)))
        self.assertEqual(d["summary"]["unique_raw_pixel_observations"],77)
        self.assertEqual(d["summary"]["distinct_candidate_cell_hours"],66)
        self.assertEqual(d["summary"]["distinct_cells_across_window"],11)
        self.assertEqual(d["summary"]["multi_sensor_cell_hours"],11)
        self.assertEqual(d["summary"]["median_bin_cell_hours"],5.5)
        self.assertEqual(d["summary"]["mad_bin_cell_hours"],3.0)
        self.assertEqual(d["summary"]["theil_sen_cell_hours_per_hour"],0.5)
        self.assertEqual(d["summary"]["later_minus_earlier_cell_hours"],36)
        self.assertEqual(d["summary"]["later_to_earlier_cell_hours_ratio"],3.4)
        self.assertEqual(d["summary"]["delayed_captures_in_later_observation_bin"],0)
        self.assertEqual(d["summary"]["capture_lag_hours_median"],0.583)
        self.assertEqual(d["scan_source_states"][FIRMS_SOURCES[0]+":complete"],12)
        self.assertEqual(d["scan_source_states"][FIRMS_SOURCES[1]+":complete"],12)
        self.assertEqual(len(d["provenance_receipts"]),12)
        self.assertEqual(len(d["provenance_receipts_sha256"]),64)
        self.assertEqual(d["verified_fire_count"],None)
        self.assertEqual(d["wildfire_probability"],None)
        self.assertEqual(d["observation_adjusted_wildfire_frequency"],None)
        self.assertIn("not a satellite pass",d["warnings"][1])
        html=render_html(d)
        self.assertIn("FIRMS historical statistical analysis",html)
        self.assertIn("Theil-Sen cell-hours/hour",html)
        self.assertIn("Unavailable" if False else "0.5",html)
        self.assertNotIn("<script",html.lower())
        self.assertNotIn("http:",html.lower())

    def test_source_filter_completes_only_its_own_source_but_not_other_failed(self):
        for i in range(12):
            states={s:"complete" for s in FIRMS_SOURCES}
            if i==5:
                states[FIRMS_SOURCES[0]]="failed"
            self.scan(i,[self.observation(i,0,source=FIRMS_SOURCES[1])],
                      states=states)
        import_release_assets(self.db,self.assets)
        both=self.report()
        self.assertEqual(both["bin_quality"]["bins_with_all_selected_sources_complete_receipts"],11)
        self.assertEqual(both["bin_quality"]["bins_without_a_complete_receipt_for_every_selected_source"],1)
        self.assertIsNone(both["summary"]["median_bin_cell_hours"])
        self.assertIsNone(both["summary"]["theil_sen_cell_hours_per_hour"])
        self.assertEqual(both["summary"]["distinct_candidate_cell_hours"],12)
        one=self.report(source=FIRMS_SOURCES[1])
        self.assertEqual(one["bin_quality"]["bins_with_all_selected_sources_complete_receipts"],12)
        self.assertEqual(one["summary"]["median_bin_cell_hours"],1)
        self.assertEqual(one["summary"]["theil_sen_cell_hours_per_hour"],0)
        self.assertEqual(one["summary"]["later_minus_earlier_cell_hours"],0)
        self.assertEqual(one["summary"]["later_to_earlier_cell_hours_ratio"],1)
        self.assertEqual(one["summary"]["multi_sensor_cell_hours"],0)

    def test_sparse_research_archive_is_unknown_not_zero_fire_or_model_trend(self):
        self.scan(0,[self.observation(0,0)])
        self.scan(11,[self.observation(11,0)])
        import_release_assets(self.db,self.assets)
        r=self.report()
        self.assertEqual(r["bin_quality"]["bins_with_no_receipt"],10)
        self.assertEqual(r["summary"]["distinct_candidate_cell_hours"],2)
        self.assertEqual(r["summary"]["unique_raw_pixel_observations"],2)
        self.assertFalse(r["bin_quality"]["trend_descriptive_only_available"])
        self.assertIsNone(r["summary"]["later_minus_earlier_cell_hours"])
        self.assertIsNone(r["summary"]["later_to_earlier_cell_hours_ratio"])
        self.assertIsNone(r["summary"]["median_bin_cell_hours"])
        self.assertTrue(any("MISSING EVIDENCE" in w for w in r["warnings"]))
        self.assertTrue(all(b["collection_evidence"]=="no_receipt"
                            for b in r["bins"][1:11]))
        self.assertIsNone(r["verified_nonfire_count"])

    def test_no_scans_or_pixels_does_not_create_negative_labels(self):
        self.scan(0,[])
        import_release_assets(self.db,self.assets)
        r=self.report()
        self.assertEqual(r["summary"]["distinct_candidate_cell_hours"],0)
        self.assertEqual(r["bin_quality"]["bins_with_no_receipt"],11)
        self.assertIsNone(r["summary"]["theil_sen_cell_hours_per_hour"])
        self.assertIsNone(r["verified_fire_count"])
        self.assertIsNone(r["verified_nonfire_count"])

    def test_first_captured_after_decision_time_is_not_visible_in_past(self):
        first=START+timedelta(hours=1)
        early=self.observation(0,0)
        self.scan(0,[early])
        late=END-timedelta(hours=1)
        # An old thermal acquisition included in a new receipt is not part
        # of the earlier source-captured world.
        make_release(self.assets/"next-day",late,[
            pixel(FIRMS_SOURCES[1],when=first,latitude=0,longitude=10.2,ident="late-backfill")])
        import_release_assets(self.db,self.assets)
        before=self.report(at=(END-timedelta(hours=2)).isoformat())
        self.assertEqual(before["summary"]["unique_raw_pixel_observations"],1)
        self.assertEqual(before["scan_receipts"],1)
        after=self.report()
        self.assertEqual(after["summary"]["unique_raw_pixel_observations"],2)
        self.assertEqual(after["scan_receipts"],2)
        self.assertEqual(after["summary"]["delayed_captures_in_later_observation_bin"],1)

    def test_explicit_receipt_capture_clock_gate_excludes_just_finished_scan(self):
        self.scan(0,[self.observation(0,0)])
        import_release_assets(self.db,self.assets)
        early=self.report(at=(START+timedelta(hours=1,minutes=2)).isoformat())
        self.assertEqual(early["scan_receipts"],0)
        self.assertEqual(early["summary"]["unique_raw_pixel_observations"],0)
        after=self.report(at=(START+timedelta(hours=1,minutes=10)).isoformat())
        self.assertEqual(after["scan_receipts"],1)
        self.assertEqual(after["summary"]["unique_raw_pixel_observations"],1)

    def test_worldwide_dateline_scope_and_same_cell_hour_sensor_dedup(self):
        self.scan(0,[self.observation(0,0,lon=179.91),
                     self.observation(0,0,source=FIRMS_SOURCES[1],lon=179.91),
                     self.observation(0,1,lon=-179.91),
                     self.observation(0,2,lon=0)])
        import_release_assets(self.db,self.assets)
        r=self.report(latitude=0,longitude=179.95,radius_km=40)
        self.assertEqual(r["summary"]["unique_raw_pixel_observations"],3)
        self.assertEqual(r["summary"]["distinct_candidate_cell_hours"],2)
        self.assertEqual(r["summary"]["multi_sensor_cell_hours"],1)

    def test_input_and_nonexistent_data_fail_without_creating_new_storage(self):
        cases=[
            {"hours":6},{"hours":333},{"radius_km":251},
            {"latitude":91},{"longitude":181},{"source":"nifc_wfigs"},
            {"radius_km":float("nan")},{"at":"not-a-date"}
        ]
        for kw in cases:
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                self.report(**kw)
        with self.assertRaises(FileNotFoundError):
            analyze_historical_signals(self.root/"missing.sqlite3",
                at=END.isoformat(),hours=24,latitude=0,longitude=10,radius_km=100)
        self.assertFalse(self.db.exists())

    def test_cli_creates_json_and_html_new_only_and_no_network_assets(self):
        self.scan(0,[self.observation(0,0)])
        import_release_assets(self.db,self.assets)
        out_json=self.root/"analysis.json"
        out_html=self.root/"analysis.html"
        command=[sys.executable,"-m","fire_public.historical_signal_analysis",
            "--pixel-db",str(self.db),"--at",END.isoformat(),"--hours","24",
            "--latitude","0","--longitude","10","--radius-km","100",
            "--json",str(out_json),"--html",str(out_html)]
        result=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        output=json.loads(result.stdout)
        self.assertEqual(output["raw_pixels"],1)
        self.assertFalse(output["forecast_generated"])
        self.assertEqual(json.loads(out_json.read_text())["summary"]["distinct_candidate_cell_hours"],1)
        self.assertIn("<html",out_html.read_text())
        before=out_json.read_bytes()
        repeated=subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(repeated.returncode,0)
        self.assertEqual(out_json.read_bytes(),before)
        self.assertEqual(self.db.stat().st_size>0,True)


if __name__=="__main__":
    unittest.main()
