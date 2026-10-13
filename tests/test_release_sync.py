"""Offline end-to-end tests of the official research Release sync protocol.

Mocks metadata/download transport, but uses real gzip files, release scan
receipts, original PixelArchive, and SQLite importer and coverage queries.
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
from fire_public.release_sync import discover, sync_releases, _plan_one

STAMP = datetime(2026, 10, 12, 18, 17, tzinfo=timezone.utc)
REPO = "frogiraffe/wildfire-signals"


def _one_pixel(at):
    when = at - timedelta(hours=1)
    fields = {"latitude":"0.015","longitude":"179.9",
              "acq_date":when.date().isoformat(),"acq_time":when.strftime("%H%M")}
    source = FIRMS_SOURCES[0]
    raw = json.dumps(fields,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    return {"kind":"thermal_detection","source":source,
            "source_fields":fields,"source_record_id":f"{source}:{digest}",
            "content_sha256":digest,"candidate_id":"firms-"+digest[:20],
            "observed_at":when.isoformat(),"received_at":at.isoformat(),
            "latitude":0.015,"longitude":179.9,"frp_mw":12.5,
            "source_url":"https://firms.modaps.eosdis.nasa.gov/api/area/",
            "rights_url":"https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy"}


def _release_files(root, at, with_pixel=True):
    root.mkdir(parents=True,exist_ok=True)
    files = []
    if with_pixel:
        with PixelArchive(root,at=at) as writer:
            writer.append(_one_pixel(at))
        assert writer.path
        files.append({"name":writer.path.name,
                      "sha256":hashlib.sha256(writer.path.read_bytes()).hexdigest()})
    stamp = at.strftime("%Y%m%dT%H%M%SZ")
    scan = {"schema_version":1,"role":"firms_pixel_scan_receipt",
            "scan_at":at.isoformat(),"captured_at":(at+timedelta(minutes=5)).isoformat(),
            "snapshot_key":"snapshot:"+"a"*64,
            "source_states":{key:"complete" for key in FIRMS_SOURCES},
            "pixel_files":files}
    compressed = gzip.compress(json.dumps(scan,sort_keys=True,separators=(",",":")).encode(),mtime=0)
    scan_path=root/f"firms-pixel-scan-{stamp}-{hashlib.sha256(compressed).hexdigest()[:16]}.json.gz"
    scan_path.write_bytes(compressed)
    tag = "analysis-evidence-"+at.date().isoformat()
    assets = []
    for path in root.iterdir():
        content=path.read_bytes()
        assets.append({"name":path.name,"size":len(content),
                       "digest":"sha256:"+hashlib.sha256(content).hexdigest(),
                       "browser_download_url":f"https://github.com/{REPO}/releases/download/{tag}/{path.name}"})
    return {"tag_name":tag,"draft":False,"prerelease":True,"assets":assets}


class ReleaseSyncTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.input=self.root/"official"
        self.destination=self.root/"downloaded"
        self.database=self.root/"history.sqlite3"
        self.record=_release_files(self.input,STAMP)
        self.data={a["browser_download_url"]:(self.input/a["name"]).read_bytes()
                   for a in self.record["assets"]}
        self.calls=[]

    def list_page(self,page):
        self.calls.append(("list",page))
        return [self.record] if page==1 else []

    def download(self,url,target,size):
        self.calls.append(("get",url))
        target.write_bytes(self.data[url])
        if len(self.data[url]) != size:
            raise ValueError("test fixture metadata download-size mismatch")
        return hashlib.sha256(self.data[url]).hexdigest()

    def sync(self,**kwargs):
        return sync_releases(self.destination,list_page=self.list_page,
                             download=self.download,**kwargs)

    def test_complete_real_receipt_to_sqlite_and_global_query(self):
        from fire_public.pixel_history import import_release_assets,coverage_report
        result=self.sync()
        self.assertEqual(result["downloaded_releases"],1)
        self.assertEqual(result["skipped_verified_releases"],0)
        imported=import_release_assets(self.database,self.destination)
        self.assertEqual(imported["new_unique_pixels"],1)
        stats=coverage_report(self.database,at=(STAMP+timedelta(hours=1)).isoformat(),
                              hours=6,latitude=0,longitude=-179.95,radius_km=40)
        self.assertEqual(stats["unique_raw_pixel_observations"],1)
        self.assertEqual(stats["candidate_cell_hours"],1)
        self.assertEqual(stats["latest_source_state"][FIRMS_SOURCES[0]]["status"],"complete")
        self.assertFalse(stats["fire_confirmation"])
        gets_before=sum(call[0]=="get" for call in self.calls)
        again=self.sync()
        self.assertEqual(again["downloaded_releases"],0)
        self.assertEqual(again["skipped_verified_releases"],1)
        self.assertEqual(sum(call[0]=="get" for call in self.calls),gets_before)
        self.assertEqual(import_release_assets(self.database,self.destination)["imported_scans"],0)

    def test_two_scans_in_one_daily_release_import_atomically_and_replay(self):
        from fire_public.pixel_history import import_release_assets
        second=_release_files(self.root/"second",STAMP+timedelta(hours=5))
        self.assertEqual(second["tag_name"],self.record["tag_name"])
        self.record["assets"].extend(second["assets"])
        self.data.update({a["browser_download_url"]:(self.root/"second"/a["name"]).read_bytes()
                          for a in second["assets"]})
        planned=discover(list_page=self.list_page)
        self.assertEqual(len(planned[0]["scan_names"]),2)
        self.assertEqual(self.sync()["downloaded_releases"],1)
        imported=import_release_assets(self.database,self.destination)
        self.assertEqual(imported["imported_scans"],2)
        self.assertEqual(self.sync()["skipped_verified_releases"],1)
        self.assertEqual(import_release_assets(self.database,self.destination)["imported_scans"],0)

    def test_orphan_pixel_in_multi_scan_release_is_rejected_before_download(self):
        second=_release_files(self.root/"second",STAMP+timedelta(hours=5))
        self.record["assets"].extend(a for a in second["assets"]
                                     if a["name"].startswith("firms-pixels"))
        with self.assertRaisesRegex(ValueError,"matching scan|orphan"):
            self.sync()
        self.assertFalse(self.destination.exists())

    def test_bad_download_digest_cannot_publish_partial_day(self):
        for key,value in list(self.data.items()):
            if "firms-pixels" in key:
                self.data[key]=value+b"x"
        with self.assertRaisesRegex(ValueError,"SHA-256|download-size"):
            self.sync()
        self.assertFalse(any(self.destination.glob("analysis-evidence-*")))
        self.assertFalse(any(self.destination.glob(".wildfire-sync-*")))

    def test_missing_pixel_in_release_metadata_rejected_before_download(self):
        self.record["assets"]=[asset for asset in self.record["assets"]
                               if asset["name"].startswith("firms-pixel-scan")]
        with self.assertRaisesRegex(ValueError,"do not match scan receipt manifest"):
            self.sync()
        self.assertFalse(any(self.destination.glob("analysis-evidence-*")))

    def test_existing_download_tamper_rejected_without_overwrite(self):
        self.sync()
        pixel=next(self.destination.rglob("firms-pixels-*.jsonl.gz"))
        pixel.write_bytes(pixel.read_bytes()+b"tamper")
        with self.assertRaisesRegex(ValueError,"hash conflict"):
            self.sync()
        self.assertTrue(pixel.read_bytes().endswith(b"tamper"))

    def test_api_url_or_asset_path_injection_rejected(self):
        self.record["assets"][0]["browser_download_url"]="https://attacker.example.org/steal"
        with self.assertRaisesRegex(ValueError,"not canonical"):
            self.sync()
        self.assertFalse(self.destination.exists())
        self.record=_release_files(self.root/"restored",STAMP)
        self.record["assets"][0]["name"]="../oops"
        with self.assertRaisesRegex(ValueError,"unexpected research release asset"):
            _plan_one(self.record)

    def test_missing_digest_or_inaccurate_size_rejected(self):
        self.record["assets"][0]["digest"]=None
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            self.sync()
        self.record=_release_files(self.root/"restored",STAMP)
        self.record["assets"][0]["size"]=0
        with self.assertRaisesRegex(ValueError,"invalid release asset size"):
            self.sync()

    def test_research_filter_bounds_and_sort_order(self):
        newer=_release_files(self.root/"newer",STAMP+timedelta(days=1),with_pixel=False)
        other={"tag_name":"v1.0","draft":False,"prerelease":False,"assets":[]}
        pages=lambda page: ([newer,self.record,other] if page==1 else [])
        output=discover(list_page=pages,max_releases=2)
        self.assertEqual([a["tag"] for a in output],
            ["analysis-evidence-2026-10-12","analysis-evidence-2026-10-13"])
        output=discover(list_page=pages,since="2026-10-13")
        self.assertEqual(len(output),1)
        with self.assertRaises(ValueError):
            discover(max_releases=0,list_page=pages)

    def test_budget_rejection_leaves_no_downloaded_files(self):
        with self.assertRaisesRegex(ValueError,"download budget"):
            self.sync(max_total_bytes=1)
        self.assertFalse(self.destination.exists())

    def test_empty_releases_report_absence_of_archive_only(self):
        result=sync_releases(self.destination,list_page=lambda page:[],
                             download=self.download)
        self.assertEqual(result["discovered_releases"],0)
        self.assertIn("not no wildfires",result["note"])

    def test_actual_github_read_does_not_run_in_tests(self):
        # Explicitly exercise trusted API URL construction while keeping all
        # network calls mocked; CI must not require token or public availability.
        import inspect
        from fire_public.release_sync import _get_releases, _download
        self.assertIn("api.github.com",inspect.getsource(_get_releases))
        self.assertIn("_TrustedRedirect",inspect.getsource(_download))


if __name__=="__main__":
    unittest.main()
