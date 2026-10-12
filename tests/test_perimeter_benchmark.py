"""End-to-end retrospective positive-only polygon benchmark regressions.

Generates authentic PixelArchive compressed JSONL + scan receipts, imports
through the real SQLite importer, and evaluates operator-provided GeoJSON.
No synthetic software fixture is reported as empirical wildfire accuracy.
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
from fire_public.pixel_history import import_release_assets
from fire_public.perimeter_benchmark import (load_reference,point_in_perimeter,
                                              benchmark_perimeters,render_html)

START=datetime(2026,10,10,6,0,tzinfo=timezone.utc)
CAPTURE=datetime(2026,10,12,12,0,tzinfo=timezone.utc)
CUTOFF=datetime(2026,10,15,0,0,tzinfo=timezone.utc)
PUBLISHED=datetime(2026,10,14,0,0,tzinfo=timezone.utc)
SOURCE_URL="https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/EDW_MTBS_v1/FeatureServer/0"

def polygon(lon1=179.7,lon2=-179.7,lat1=9.7,lat2=10.3):
    return [[lon1,lat1],[lon2,lat1],[lon2,lat2],[lon1,lat2],[lon1,lat1]]

def feature(identifier="wild-1", *, kind="Wildfire", coords=None,
            name="Reference fire", ignition=START, geometry_type="Polygon"):
    if coords is None:
        coords=[polygon()]
    return {"type":"Feature","properties":{
       "FIRE_ID":identifier,"FIRE_NAME":name,"FIRE_TYPE":kind,
       "IG_DATE":int(ignition.timestamp()*1000)},
       "geometry":{"type":geometry_type,"coordinates":coords}}

def raw_pixel(when,lat=10.0,lon=-179.9,source=FIRMS_SOURCES[0],extra=""):
    fields={"latitude":str(lat),"longitude":str(lon),
            "acq_date":when.date().isoformat(),"acq_time":when.strftime("%H%M"),
            "user_visible_tag":extra}
    digest=hashlib.sha256(json.dumps(fields,separators=(",",":"),sort_keys=True,
        ensure_ascii=False).encode()).hexdigest()
    return {"kind":"thermal_detection","source":source,
            "source_fields":fields,"source_record_id":f"{source}:{digest}",
            "content_sha256":digest,"candidate_id":"firms-"+digest[:20],
            "observed_at":when.isoformat(),"latitude":lat,"longitude":lon,
            "frp_mw":12.0,"source_url":"https://firms.modaps.eosdis.nasa.gov/api/area/",
            "rights_url":"https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy"}

def release(folder,at,rows,states=None):
    folder.mkdir(parents=True,exist_ok=True)
    states=states or {s:"complete" for s in FIRMS_SOURCES}
    pixel_assets=[]
    for source in FIRMS_SOURCES:
        matching=[row for row in rows if row["source"]==source]
        if not matching:continue
        with PixelArchive(folder,at=at) as writer:
            for row in matching:
                writer.append({**row,"received_at":at.isoformat()})
        assert writer.path
        pixel_assets.append({"name":writer.path.name,
            "sha256":hashlib.sha256(writer.path.read_bytes()).hexdigest()})
    receipt={"schema_version":1,"role":"firms_pixel_scan_receipt",
             "scan_at":at.isoformat(),
             "captured_at":(at+timedelta(minutes=5)).isoformat(),
             "snapshot_key":"snapshot:"+"a"*64,
             "source_states":states,"pixel_files":pixel_assets}
    raw=gzip.compress(json.dumps(receipt,separators=(",",":"),sort_keys=True).encode(),mtime=0)
    stamp=at.strftime("%Y%m%dT%H%M%SZ")
    (folder/f"firms-pixel-scan-{stamp}-{hashlib.sha256(raw).hexdigest()[:16]}.json.gz").write_bytes(raw)

class PerimeterBenchmarkTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.folder=self.root/"assets"
        self.db=self.root/"pixels.sqlite3"
        self.geo=self.root/"reference.geojson"

    def write_features(self,features):
        self.geo.write_text(json.dumps({"type":"FeatureCollection","features":features}),
                            encoding="utf-8")
        return self.reference()

    def reference(self,published=PUBLISHED):
        return load_reference(self.geo,source_url=SOURCE_URL,
                              published_at=published.isoformat())

    def import_pixels(self,rows=None,at=CAPTURE,states=None):
        if rows is None:
            rows=[raw_pixel(START+timedelta(hours=10))]
        release(self.folder,at,rows,states)
        return import_release_assets(self.db,self.folder)

    def test_true_archive_intersection_and_unsupported_fire_classes_excluded(self):
        ref=self.write_features([
            feature(),feature("rx",kind="Prescribed Fire"),
            feature("unknown",kind="Unknown"),
            feature("wild-2",coords=[polygon(30,31,10,11)],name="Missing fire")])
        self.assertEqual(ref["included_wildfire_features"],2)
        self.assertEqual(ref["excluded"]["prescribed_or_unknown_fire_type"],2)
        self.import_pixels([raw_pixel(START+timedelta(hours=10)),
                            raw_pixel(START+timedelta(hours=11),lon=170.0,extra="outside"),
                            raw_pixel(START+timedelta(hours=12),source=FIRMS_SOURCES[1],
                                      lon=179.8,extra="inside2")])
        report=benchmark_perimeters(self.db,ref,as_of=CUTOFF.isoformat(),
                                    observation_days=3)
        self.assertEqual(report["evaluated_reference_perimeters"],2)
        self.assertEqual(report["reference_polygons_with_pixel_intersections"],1)
        self.assertEqual(report["with_any_eligible_collector_receipts"],2)
        self.assertEqual(report["total_pixel_polygon_intersections"],2)
        fire=next(e for e in report["events"] if e["fire_id"]=="wild-1")
        self.assertEqual(fire["pixels_intersecting_final_perimeter"],2)
        self.assertEqual(len(fire["intersecting_pixels_by_sensor"]),2)
        missing=next(e for e in report["events"] if e["fire_id"]=="wild-2")
        self.assertEqual(missing["outcome"],"no_intersection_in_archived_pixels")
        self.assertTrue(missing["not_negative_label"])
        self.assertEqual(report["valid_negative_labels_created"],0)
        self.assertFalse(report["independent_wildfire_detection_accuracy_established"])
        self.assertFalse(report["source_observation_completeness_verified"])
        self.assertTrue(report["reference"]["file_sha256"])

    def test_hole_multipolygon_and_international_dateline_geometry(self):
        from fire_public.perimeter_benchmark import _polygons
        hole=[[179.85,9.9],[-179.85,9.9],[-179.85,10.1],
              [179.85,10.1],[179.85,9.9]]
        multi=_polygons({"type":"MultiPolygon","coordinates":[
            [polygon(),hole], [polygon(30,31,10,11)]]})
        self.assertFalse(point_in_perimeter(10,-179.9,multi)) # hole
        self.assertTrue(point_in_perimeter(10,-179.75,multi))
        self.assertTrue(point_in_perimeter(10,30.5,multi))
        self.assertFalse(point_in_perimeter(10,50,multi))
        self.assertFalse(point_in_perimeter(0,-179.9,multi))

    def test_later_collected_pixels_and_retrospective_publication_cutoff(self):
        ref=self.write_features([feature()])
        self.import_pixels()
        with self.assertRaisesRegex(ValueError,"not published"):
            benchmark_perimeters(self.db,ref,as_of=(PUBLISHED-timedelta(hours=1)).isoformat(),
                                 observation_days=3)
        report=benchmark_perimeters(self.db,ref,as_of=CUTOFF.isoformat(),
                                    observation_days=3)
        self.assertEqual(report["reference_polygons_with_pixel_intersections"],1)
        self.assertEqual(report["events"][0]["first_intersecting_pixel_captured_at"],
                         (CAPTURE+timedelta(minutes=5)).isoformat())

    def test_missing_scans_abstain_rather_than_negative_label(self):
        self.write_features([feature()])
        release(self.folder,CAPTURE+timedelta(days=10),[])  # outside event window
        import_release_assets(self.db,self.folder)
        report=benchmark_perimeters(self.db,self.reference(),as_of=(CUTOFF+timedelta(days=12)).isoformat(),observation_days=3)
        self.assertEqual(report["with_any_eligible_collector_receipts"],0)
        self.assertEqual(report["events"][0]["outcome"],"unassessed_no_collector_evidence")
        self.assertIsNone(report["reference_overlap_fraction_given_some_receipts"])

    def test_failed_source_receipt_is_not_evidence_of_no_fire(self):
        self.write_features([feature()])
        self.import_pixels([],states={FIRMS_SOURCES[0]:"failed",
                                      FIRMS_SOURCES[1]:"complete"})
        report=benchmark_perimeters(self.db,self.reference(),as_of=CUTOFF.isoformat(),observation_days=3)
        self.assertEqual(report["events"][0]["collection_evidence"],"incomplete_source_scans")
        self.assertEqual(report["events"][0]["pixels_intersecting_final_perimeter"],0)
        self.assertEqual(report["valid_negative_labels_created"],0)

    def test_after_event_window_reference_excluded(self):
        self.write_features([feature()])
        self.import_pixels()
        report=benchmark_perimeters(self.db,self.reference(),as_of=(PUBLISHED+timedelta(hours=1)).isoformat(),
                                    observation_days=7)
        self.assertEqual(report["perimeters_after_cutoff_excluded"],1)
        self.assertEqual(report["evaluated_reference_perimeters"],0)

    def test_reference_identity_schema_safety_and_date_fallback(self):
        a=feature()
        a["properties"].pop("IG_DATE")
        a["properties"].update(YEAR=2026,STARTMONTH=10,STARTDAY=10)
        ref=self.write_features([a])
        self.assertEqual(ref["perimeters"][0]["ignition_at"],"2026-10-10T00:00:00+00:00")
        with self.assertRaisesRegex(ValueError,"duplicate"):
            self.write_features([feature(),feature()])
        evil=feature()
        evil["geometry"]["coordinates"]=[[[250,0],[1,0],[1,1],[250,0]]]
        with self.assertRaisesRegex(ValueError,"lon/lat"):
            self.write_features([evil])
        openring=feature()
        openring["geometry"]["coordinates"]=[[[0,0],[1,0],[1,1],[0,1]]]
        with self.assertRaisesRegex(ValueError,"not closed"):
            self.write_features([openring])

    def test_geojson_html_escape_bad_uri_and_bounded_reference_file(self):
        feature_x=feature(name="<script>alert(1)</script>")
        ref=self.write_features([feature_x])
        self.import_pixels()
        report=benchmark_perimeters(self.db,ref,as_of=CUTOFF.isoformat(),observation_days=3)
        page=render_html(report)
        self.assertIn("&lt;script&gt;",page)
        self.assertNotIn("<script>alert(1)</script>",page)
        with self.assertRaisesRegex(ValueError,"HTTPS"):
            load_reference(self.geo,source_url="javascript:alert(1)",
                           published_at=PUBLISHED.isoformat())
        with self.assertRaises(ValueError):
            benchmark_perimeters(self.db,ref,as_of=CUTOFF.isoformat(),observation_days=0)
        with self.assertRaisesRegex(ValueError,"missing"):
            load_reference(self.root/"absent.geojson",source_url=SOURCE_URL,
                           published_at=PUBLISHED.isoformat())

    def test_cli_reports_json_html_and_rejects_overwrite_of_evidence(self):
        self.write_features([feature()])
        self.import_pixels()
        j=self.root/"report.json";h=self.root/"report.html"
        args=[sys.executable,"-m","fire_public.perimeter_benchmark",
              "--pixel-db",str(self.db),"--geojson",str(self.geo),
              "--source-url",SOURCE_URL,"--reference-published-at",PUBLISHED.isoformat(),
              "--as-of",CUTOFF.isoformat(),"--observation-days","3",
              "--json",str(j),"--html",str(h)]
        first=subprocess.run(args,capture_output=True,text=True)
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(json.loads(j.read_text())["reference_polygons_with_pixel_intersections"],1)
        self.assertIn("Retrospective Burned-Area Overlap",h.read_text())
        again=subprocess.run(args,capture_output=True,text=True)
        self.assertNotEqual(again.returncode,0)
        altered=args[:]
        altered[altered.index("--json")+1]=str(self.db)
        altered+=["--overwrite"]
        rejected=subprocess.run(altered,capture_output=True,text=True)
        self.assertNotEqual(rejected.returncode,0)
        self.assertIn("cannot overwrite",rejected.stderr)
        self.assertTrue(self.db.is_file())

if __name__=="__main__":
    unittest.main()
