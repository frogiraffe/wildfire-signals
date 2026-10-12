"""End-to-end historical agency + verified raw pixel research SQLite contract.

Tests exercise actual recorded PixelArchive files and as-of Workbench/Change
Explorer execution. FIxtures are illustrative, NOT real wildfire statistics.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fire_public.collect import FIRMS_SOURCES
from fire_public.history import HistoryStore
from fire_public.pixel_archive import PixelArchive
from fire_public.pixel_history import import_release_assets
from fire_public.intelligence_workbench import build_workbench,render_html
from fire_public.change_explorer import compare_archive,compare_reports,render_changes_html

FIRST=datetime(2026,10,12,12,17,tzinfo=timezone.utc)
SECOND=datetime(2026,10,12,18,17,tzinfo=timezone.utc)


def pixel(at, observed, source, lon):
    fields={"latitude":"0.0","longitude":str(lon),
            "acq_date":observed.date().isoformat(),
            "acq_time":observed.strftime("%H%M")}
    raw=json.dumps(fields,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    digest=hashlib.sha256(raw).hexdigest()
    return {"kind":"thermal_detection","source":source,
            "source_fields":fields,"source_record_id":f"{source}:{digest}",
            "content_sha256":digest,"candidate_id":"firms-"+digest[:20],
            "observed_at":observed.isoformat(),"received_at":at.isoformat(),
            "latitude":0.0,"longitude":lon,"frp_mw":10.0,
            "source_url":"https://firms.modaps.eosdis.nasa.gov/api/area/",
            "rights_url":"https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy"}


def release(root, scan_at, rows):
    root.mkdir(parents=True,exist_ok=True)
    files=[]
    for source,events in ((name,[x for x in rows if x["source"]==name])
                          for name in FIRMS_SOURCES):
        if not events:
            continue
        with PixelArchive(root,at=scan_at) as archive:
            for row in events:
                archive.append(row)
        path=archive.path
        assert path is not None
        files.append({"name":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest={"schema_version":1,"role":"firms_pixel_scan_receipt",
              "scan_at":scan_at.isoformat(),
              "captured_at":(scan_at+timedelta(minutes=5)).isoformat(),
              "snapshot_key":"snapshot:"+"a"*64,
              "source_states":{source:"complete" for source in FIRMS_SOURCES},
              "pixel_files":files}
    compressed=gzip.compress(json.dumps(manifest,sort_keys=True,separators=(",",":")).encode(),mtime=0)
    stamp=scan_at.strftime("%Y%m%dT%H%M%SZ")
    (root/f"firms-pixel-scan-{stamp}-{hashlib.sha256(compressed).hexdigest()[:16]}.json.gz").write_bytes(compressed)


class WorkbenchPixelsTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.agency_db=self.root/"agency.sqlite3"
        self.pixel_db=self.root/"pixel.sqlite3"
        self.artifacts=self.root/"releases"
        self.agency=HistoryStore(self.agency_db)
        self.addCleanup(self.agency.close)
        self.agency.append({
            "subject_kind":"agency_incident","provider":"cwfis","source_id":"example",
            "record_type":"incident_status","observed_at":"2026-10-12T09:00:00Z",
            "captured_at":"2026-10-12T10:00:00Z",
            "source_url":"https://example.org/agency",
            "rights_url":"https://example.org/rights",
            "payload":{"name":"Example record","agency_status":"OC",
                       "latitude":0.0,"longitude":179.9}})
        # An unrelated candidate record in the agency database must not be
        # added to the separate, authenticated raw release pixel totals.
        self.agency.append({
            "subject_kind":"satellite_candidate","provider":"firms",
            "source_id":"agency-candidate","record_type":"thermal_observation",
            "observed_at":"2026-10-12T11:00:00Z",
            "captured_at":"2026-10-12T11:10:00Z",
            "source_url":"https://example.org/satellite",
            "rights_url":"https://example.org/rights",
            "payload":{"latitude":0.0,"longitude":179.9,"sources":["NOAA-20"]}})
        initial=pixel(FIRST,FIRST-timedelta(hours=1),FIRMS_SOURCES[0],179.9)
        late=pixel(SECOND,SECOND-timedelta(hours=1),FIRMS_SOURCES[1],-179.9)
        release(self.artifacts/"day1",FIRST,[initial])
        release(self.artifacts/"day2",SECOND,[
            pixel(SECOND,FIRST-timedelta(hours=1),FIRMS_SOURCES[0],179.9),late])
        import_release_assets(self.pixel_db,self.artifacts)

    def scope(self):
        return {"latitude":0.0,"longitude":179.95,"radius_km":50}

    def test_as_of_raw_archive_report_is_not_double_counted(self):
        early=build_workbench(self.agency_db,at="2026-10-12T14:00:00Z",
                              pixel_db=self.pixel_db,**self.scope())
        late=build_workbench(self.agency_db,at="2026-10-12T19:00:00Z",
                             pixel_db=self.pixel_db,**self.scope())
        before=early["satellite_evidence"]
        after=late["satellite_evidence"]
        self.assertEqual(before["origin"],"verified_release_pixel_sqlite")
        self.assertEqual(before["available_archive_records"],1)
        self.assertEqual(after["available_archive_records"],2)
        self.assertEqual(after["candidate_cell_hours"],2)
        self.assertEqual(after["distinct_observed_cells"],2)
        self.assertEqual(after["scan_count"],2)
        self.assertEqual(after["observation_unit"],"raw_viirs_pixels")
        self.assertEqual(len(late["incidents"]),1)
        self.assertEqual(late["incidents"][0]["provider"],"cwfis")
        self.assertTrue(after["no_fire_inference"])
        html=render_html(late)
        self.assertIn("raw_viirs_pixels",html)
        self.assertIn("Grouped 0.05° candidate cell-hours",html)
        self.assertIn("source:",html)

    def test_compare_replays_both_times_using_same_raw_archive(self):
        result=compare_archive(self.agency_db,pixel_db=self.pixel_db,
                earlier_at="2026-10-12T14:00:00Z",
                later_at="2026-10-12T19:00:00Z",**self.scope())
        self.assertEqual(result["satellite"]["earlier"]["available_archive_records"],1)
        self.assertEqual(result["satellite"]["later"]["available_archive_records"],2)
        self.assertEqual(result["agency"]["changed_events"],[])
        self.assertEqual(result["wildfire_outcome_labels_created"],0)
        self.assertIn("Historical Evidence Change Explorer",render_changes_html(result))

    def test_refuse_mixed_archive_sources_in_manual_comparison(self):
        earlier=build_workbench(self.agency_db,at="2026-10-12T14:00:00Z",**self.scope())
        later=build_workbench(self.agency_db,at="2026-10-12T19:00:00Z",
                              pixel_db=self.pixel_db,**self.scope())
        with self.assertRaisesRegex(ValueError,"provenance must be the same"):
            compare_reports(earlier,later)

    def test_explicit_missing_pixel_archive_fails(self):
        with self.assertRaises(FileNotFoundError):
            build_workbench(self.agency_db,at="2026-10-12T19:00:00Z",
                            pixel_db=self.root/"missing.sqlite3",**self.scope())

    def test_cli_report_compare_html_json_and_source_db_overwrite_guard(self):
        command=[sys.executable,"-m","fire_public.intelligence_workbench"]
        report=self.root/"report.json"
        cmd=command+["report","--db",str(self.agency_db),
                     "--pixel-db",str(self.pixel_db),
                     "--at","2026-10-12T19:00:00Z",
                     "--json",str(report)]
        r=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(report.read_text())["satellite_evidence"]["available_archive_records"],2)
        changes=self.root/"changes.json"
        cmd=command+["compare","--db",str(self.agency_db),
                     "--pixel-db",str(self.pixel_db),
                     "--earlier-at","2026-10-12T14:00:00Z",
                     "--later-at","2026-10-12T19:00:00Z",
                     "--json",str(changes)]
        r=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(changes.read_text())["satellite"]["later"]["available_archive_records"],2)
        blocked=cmd[:-1]+[str(self.pixel_db),"--overwrite"]
        failed=subprocess.run(blocked,capture_output=True,text=True)
        self.assertNotEqual(failed.returncode,0)
        self.assertIn("cannot overwrite",failed.stderr)


if __name__=="__main__":
    unittest.main()
