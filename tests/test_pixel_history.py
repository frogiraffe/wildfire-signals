"""Offline end-to-end research release replay with checksum and completeness gates.

Tests generate authentic PixelArchive gzip JSONL files and receipt-format
manifests but DO NOT represent measured wildfire outcomes.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fire_public.collect import FIRMS_SOURCES
from fire_public.pixel_archive import PixelArchive
from fire_public.pixel_history import import_release_assets, coverage_report

FIRST = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
SECOND = FIRST + timedelta(hours=12)
LATER = FIRST + timedelta(hours=24)


def pixel(source, *, when=FIRST, latitude=0.0, longitude=179.9, ident="one"):
    # Parser's source_fields hash is stable across captured scans.
    fields={"latitude":str(latitude),"longitude":str(longitude),
            "acq_date":when.date().isoformat(),"acq_time":when.strftime("%H%M"),
            "source_note":ident}
    digest=hashlib.sha256(json.dumps(fields,sort_keys=True,
        separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    return {"kind":"thermal_detection","source":source,
            "source_record_id":f"{source}:{digest}","content_sha256":digest,
            "source_fields":fields,"candidate_id":"firms-"+digest[:20],
            "observed_at":when.isoformat(),"received_at":None,
            "latitude":latitude,"longitude":longitude,"frp_mw":8.1,
            "source_url":"https://firms.modaps.eosdis.nasa.gov/api/area/",
            "rights_url":"https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy"}


def make_release(directory, at, items, states=None):
    directory.mkdir(parents=True,exist_ok=True)
    states=states or {name:"complete" for name in FIRMS_SOURCES}
    grouped={}
    for record in items:
        clone=dict(record,received_at=at.isoformat())
        grouped.setdefault(clone["source"],[]).append(clone)
    files=[]
    for source,records in grouped.items():
        with PixelArchive(directory,at=at) as archive:
            for record in records:
                archive.append(record)
        assert archive.path is not None
        files.append({"name":archive.path.name,
                      "sha256":hashlib.sha256(archive.path.read_bytes()).hexdigest()})
    scan={"schema_version":1,"role":"firms_pixel_scan_receipt",
          "scan_at":at.isoformat(),
          "captured_at":(at+timedelta(minutes=5)).isoformat(),
          "snapshot_key":"snapshot:"+"a"*64,
          "source_states":states,"pixel_files":files}
    data=gzip.compress(json.dumps(scan,sort_keys=True,separators=(",",":")).encode(),mtime=0)
    stamp=at.strftime("%Y%m%dT%H%M%SZ")
    digest=hashlib.sha256(data).hexdigest()[:16]
    path=directory/f"firms-pixel-scan-{stamp}-{digest}.json.gz"
    path.write_bytes(data)
    return path


class HistoricalPixelTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.assets=self.root/"assets"
        self.db=self.root/"pixels.sqlite3"

    def test_import_idempotent_and_earliest_captured_as_of(self):
        one=pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(hours=1))
        make_release(self.assets/"day1",FIRST,[one])
        make_release(self.assets/"day2",SECOND,[one, pixel(FIRMS_SOURCES[1],
                      when=SECOND-timedelta(hours=1),longitude=-179.9,ident="second")])
        result=import_release_assets(self.db,self.assets)
        self.assertEqual(result["imported_scans"],2)
        self.assertEqual(result["pixel_rows_read"],3)
        self.assertEqual(result["new_unique_pixels"],2)
        self.assertEqual(result["duplicate_observations"],1)
        again=import_release_assets(self.db,self.assets)
        self.assertEqual(again["imported_scans"],0)
        early=coverage_report(self.db,at=(FIRST+timedelta(minutes=10)).isoformat(),
                              hours=6,latitude=0,longitude=179.95,radius_km=40)
        self.assertEqual(early["unique_raw_pixel_observations"],1)
        self.assertEqual(early["completed_scan_receipts"],1)
        late=coverage_report(self.db,at=(SECOND+timedelta(minutes=10)).isoformat(),
                             hours=24,latitude=0,longitude=179.95,radius_km=40)
        self.assertEqual(late["unique_raw_pixel_observations"],2)
        self.assertEqual(late["distinct_observed_cells"],2)
        self.assertFalse(late["fire_confirmation"])
        self.assertEqual(late["evidence_completeness"],"unverified")

    def test_map_equivalent_cell_hour_aggregation_and_repeated_hours(self):
        make_release(self.assets,FIRST,[
            pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(minutes=40),
                  latitude=0.011,longitude=30.011,ident="first"),
            pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(minutes=35),
                  latitude=0.019,longitude=30.019,ident="second"),
            pixel(FIRMS_SOURCES[1],when=FIRST-timedelta(hours=1,minutes=35),
                  latitude=0.018,longitude=30.015,ident="previous-hour")])
        import_release_assets(self.db,self.assets)
        report=coverage_report(self.db,at=(FIRST+timedelta(minutes=10)).isoformat(),
                               hours=6,latitude=0.015,longitude=30.015,radius_km=20)
        self.assertEqual(report["unique_raw_pixel_observations"],3)
        self.assertEqual(report["candidate_cell_hours"],2)
        self.assertEqual(report["distinct_observed_cells"],1)
        self.assertEqual(report["cells_observed_multiple_hours"],1)
        self.assertIn("0.05 degree",report["aggregation"])

    def test_failed_source_and_empty_scan_not_interpreted_as_fire_absence(self):
        make_release(self.assets,FIRST,[],states={FIRMS_SOURCES[0]:"failed",
                                                  FIRMS_SOURCES[1]:"complete"})
        import_release_assets(self.db,self.assets)
        result=coverage_report(self.db,at=(FIRST+timedelta(hours=1)).isoformat(),hours=6)
        self.assertEqual(result["unique_raw_pixel_observations"],0)
        self.assertEqual(result["latest_source_state"][FIRMS_SOURCES[0]]["status"],"failed")
        self.assertFalse(result["fire_confirmation"])
        self.assertIn("never proves absence",result["warning"])

    def test_timestamp_cutoff_prevents_late_hindsight(self):
        make_release(self.assets,FIRST,[
            pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(hours=2))])
        make_release(self.assets/"later",LATER,[
            pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(hours=2),ident="late")])
        import_release_assets(self.db,self.assets)
        result=coverage_report(self.db,at=(FIRST+timedelta(hours=1)).isoformat(),
                               hours=6)
        self.assertEqual(result["unique_raw_pixel_observations"],1)

    def test_checksum_tamper_rolls_back_import_batch(self):
        first=make_release(self.assets/"one",FIRST,[
            pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(hours=1))])
        make_release(self.assets/"two",SECOND,[
            pixel(FIRMS_SOURCES[1],when=SECOND-timedelta(hours=1),ident="later")])
        archive=next((self.assets/"two").glob("firms-pixels-*.jsonl.gz"))
        archive.write_bytes(archive.read_bytes()+b"modified")
        with self.assertRaisesRegex(ValueError,"checksum"):
            import_release_assets(self.db,self.assets)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pixel_scans").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM pixel_observations").fetchone()[0],0)
        self.assertTrue(first.is_file())

    def test_scan_receipt_corruption_rejected(self):
        path=make_release(self.assets,FIRST,[])
        path.write_bytes(path.read_bytes()+b"tamper")
        with self.assertRaisesRegex(ValueError,"checksum"):
            import_release_assets(self.db,self.assets)

    def test_source_row_mutation_rejected_even_with_new_archive_checksums(self):
        row=pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(hours=1))
        row["content_sha256"]="0"*64
        make_release(self.assets,FIRST,[row])
        with self.assertRaisesRegex(ValueError,"provenance mismatch"):
            import_release_assets(self.db,self.assets)

    def test_missing_asset_is_not_a_complete_import(self):
        make_release(self.assets,FIRST,[
            pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(hours=1))])
        next(self.assets.glob("firms-pixels-*.jsonl.gz")).unlink()
        with self.assertRaisesRegex(ValueError,"missing or unexpected"):
            import_release_assets(self.db,self.assets)

    def test_conflicting_scan_rejected_on_repeat(self):
        make_release(self.assets,FIRST,[])
        import_release_assets(self.db,self.assets)
        for file in self.assets.iterdir():
            file.unlink()
        make_release(self.assets,FIRST,[
            pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(hours=1))])
        with self.assertRaisesRegex(ValueError,"conflicting historical pixel scan"):
            import_release_assets(self.db,self.assets)

    def test_invalid_circle_and_time_inputs(self):
        make_release(self.assets,FIRST,[])
        import_release_assets(self.db,self.assets)
        for params in ({"hours":0},{"latitude":0},{"latitude":91,"longitude":0,"radius_km":50},
                       {"latitude":0,"longitude":0,"radius_km":float("nan")}):
            with self.subTest(params=params),self.assertRaises(ValueError):
                coverage_report(self.db,at=FIRST.isoformat(),**params)

    def test_cli_import_and_report_no_archive_overwrite(self):
        make_release(self.assets,FIRST,[
            pixel(FIRMS_SOURCES[0],when=FIRST-timedelta(hours=1))])
        runner=[sys.executable,"-m","fire_public.pixel_history"]
        imported=subprocess.run(runner+["import","--assets",str(self.assets),
                                        "--db",str(self.db)],capture_output=True,text=True)
        self.assertEqual(imported.returncode,0,imported.stderr)
        out=self.root/"coverage.json"
        command=runner+["report","--db",str(self.db),
                        "--at",(FIRST+timedelta(hours=1)).isoformat(),
                        "--hours","6","--output",str(out)]
        completed=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(completed.returncode,0,completed.stderr)
        self.assertEqual(json.loads(out.read_text())["unique_raw_pixel_observations"],1)
        collision=subprocess.run(command,capture_output=True,text=True)
        self.assertNotEqual(collision.returncode,0)
        unsafe=command[:]
        unsafe[-1]=str(self.db)
        blocked=subprocess.run(unsafe,capture_output=True,text=True)
        self.assertNotEqual(blocked.returncode,0)


if __name__=="__main__":
    unittest.main()
