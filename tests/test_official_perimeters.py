"""Mock HTTP transport, real GeoJSON validation, SQLite and CLI integration.

These geometries are synthetic; they prove the importer does not infer
missing fires, negatives or retrospective prediction availability.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.official_perimeters import (
    _feature, _rings, intersects_circle, report, sync_year, RIGHTS_URL, SERVICE
)

T1="2026-10-12T12:00:00Z"
T2="2026-10-13T12:00:00Z"


def square(lat,lon,edge=0.01):
    # Polygon crossing longitude ±180 uses wrapped corner coordinates.
    normal=lambda v: ((v+180)%360)-180
    low,high=normal(lon-edge),normal(lon+edge)
    coords=[[low,lat-edge],[high,lat-edge],[high,lat+edge],
            [low,lat+edge],[low,lat-edge]]
    return {"type":"Polygon","coordinates":[coords]}


def feature(oid,*,year=2018,lat=37,lon=-120,name="Independent example"):
    return {"type":"Feature","properties":{
        "OBJECTID":oid,"GlobalID":f"{{official-guid-{oid}}}",
        "FIRE_YEAR_INT":year,"INCIDENT":name,"GIS_ACRES":100.0,
        "AGENCY":"USFS","SOURCE":"agency-perimeter"},
        "geometry":square(lat,lon)}


class FakeService:
    def __init__(self, features=None):
        self.entries=features or [feature(4),feature(5,lon=179.9,lat=60)]
        self.calls=[]
        self.bad=None

    def __call__(self, params):
        self.calls.append(dict(params))
        if params.get("returnIdsOnly")=="true":
            return {"objectIdFieldName":"OBJECTID",
                    "objectIds":[f["properties"]["OBJECTID"] for f in self.entries]}
        selected={int(s) for s in params["objectIds"].split(",")}
        rows=[v for v in self.entries if v["properties"]["OBJECTID"] in selected]
        if self.bad=="missing":rows=rows[:-1]
        if self.bad=="wrongyear":
            rows=json.loads(json.dumps(rows))
            rows[0]["properties"]["FIRE_YEAR_INT"]=2017
        if self.bad=="malformed":
            rows=json.loads(json.dumps(rows))
            rows[0]["geometry"]={"type":"Point","coordinates":[1,2]}
        return {"type":"FeatureCollection","features":rows}


class PerimeterHistoryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.db=self.root/"official.sqlite3"
        self.service=FakeService()

    def sync(self,**kwargs):
        return sync_year(self.db,year=2018,get_json=self.service,clock=lambda:T1,**kwargs)

    def test_source_ids_and_retrospective_capture(self):
        out=self.sync(max_records=2)
        self.assertEqual(out["total_source_ids"],2)
        self.assertEqual(out["fetched_perimeters"],2)
        self.assertFalse(out["subset_only"])
        self.assertFalse(out["data_complete_for_fire_occurrence"])
        self.assertTrue(out["retrospective_not_as_of_features"])
        # Historic fire_year=2018 does not make data available in 2018.
        old=report(self.db,at="2018-10-01T00:00:00Z")
        self.assertEqual(old["shown"],0)
        now=report(self.db,at=T1)
        self.assertEqual(now["shown"],2)
        self.assertEqual(now["valid_negative_labels_created"],0)
        self.assertFalse(now["model_feature_ready"])
        self.assertEqual(now["source_batches"],1)
        self.assertEqual(now["events"][0]["rights_url"],RIGHTS_URL)

    def test_explicit_limit_is_marked_partial(self):
        out=self.sync(max_records=1)
        self.assertTrue(out["subset_only"])
        rows=report(self.db,at=T1,year=2018)
        self.assertEqual(rows["shown"],1)
        self.assertTrue(rows["any_source_batch_subset_only"])
        self.assertEqual(rows["visible_unique_source_ids"],1)

    def test_same_source_id_preserves_versions_and_as_of(self):
        self.sync(max_records=2)
        self.service.entries[0]=feature(4,name="Corrected government name")
        second=sync_year(self.db,year=2018,get_json=self.service,clock=lambda:T2,max_records=2)
        self.assertNotEqual(second["batch_id"],"")
        first=report(self.db,at=T1)
        self.assertIn("Independent example",[x["name"] for x in first["events"]])
        latest=report(self.db,at=T2)
        self.assertIn("Corrected government name",[x["name"] for x in latest["events"]])
        self.assertEqual(latest["visible_unique_source_ids"],2)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM perimeter_versions").fetchone()[0],4)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM perimeter_fetches").fetchone()[0],2)

    def test_identical_batch_is_idempotent(self):
        one=self.sync(max_records=2)
        again=self.sync(max_records=2)
        self.assertEqual(one["batch_id"],again["batch_id"])
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM perimeter_fetches").fetchone()[0],1)

    def test_page_validation_rejects_missing_wrong_year_and_malformed_geometry(self):
        for failure in ("missing","wrongyear","malformed"):
            with self.subTest(failure=failure):
                self.service.bad=failure
                with self.assertRaises(ValueError):
                    self.sync(max_records=2)
                self.assertFalse(self.db.exists())
        self.service.bad=None

    def test_year_scope_and_record_budget(self):
        for year in (2019.0,2020,1890):
            with self.assertRaises(ValueError):
                sync_year(self.db,year=year,get_json=self.service)
        for cap in (0,301,True):
            with self.assertRaises(ValueError):
                self.sync(max_records=cap)
        with self.assertRaises(ValueError):
            report(self.db,at=T1,latitude=10)
        with self.assertRaises(ValueError):
            report(self.db,at=T1,radius_km=251,latitude=37,longitude=-120)

    def test_search_by_polygon_not_only_centroid_and_antimeridian(self):
        self.sync(max_records=2)
        california=report(self.db,at=T1,latitude=37.014,longitude=-120,
                          radius_km=1)
        self.assertEqual(california["shown"],1)
        self.assertEqual(california["events"][0]["object_id"],4)
        alaska=report(self.db,at=T1,latitude=60,longitude=-179.9,radius_km=15)
        self.assertEqual(alaska["shown"],1)
        self.assertEqual(alaska["events"][0]["object_id"],5)
        empty=report(self.db,at=T1,latitude=0,longitude=0,radius_km=50)
        self.assertEqual(empty["shown"],0)
        self.assertEqual(empty["valid_negative_labels_created"],0)
        self.assertTrue(empty["independent_positive_context_only"])

    def test_polygon_hole_does_not_contain_search_center(self):
        geometry={"type":"Polygon","coordinates":[
            [[-0.1,-0.1],[0.1,-0.1],[0.1,0.1],[-0.1,0.1],[-0.1,-0.1]],
            [[-0.02,-0.02],[0.02,-0.02],[0.02,0.02],[-0.02,0.02],[-0.02,-0.02]]]}
        self.assertFalse(intersects_circle(geometry,latitude=0,longitude=0,radius_km=1))
        self.assertTrue(intersects_circle(geometry,latitude=0,longitude=0,radius_km=3))

    def test_preserve_provider_source_attributes_and_original_geometry(self):
        self.sync(max_records=2)
        rows=report(self.db,at=T1)
        self.assertEqual(rows["events"][0]["source_attributes"]["AGENCY"],"USFS")
        self.assertEqual(rows["events"][0]["source_reported_acres"],100)
        self.assertEqual(rows["events"][0]["geometry"]["type"],"Polygon")
        self.assertEqual(rows["events"][0]["source_url"],SERVICE)

    def test_report_cli_json_and_geojson_outputs_and_overwrite_guard(self):
        self.sync(max_records=2)
        cmd=[sys.executable,"-m","fire_public.official_perimeters","report",
             "--db",str(self.db),"--year","2018","--at",T1,
             "--output",str(self.root/"result.json"),
             "--geojson",str(self.root/"perimeters.geojson")]
        done=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        out=json.loads((self.root/"result.json").read_text())
        geo=json.loads((self.root/"perimeters.geojson").read_text())
        self.assertEqual(out["shown"],len(geo["features"]))
        self.assertEqual(geo["type"],"FeatureCollection")
        self.assertEqual(geo["properties"]["independent_positive_context_only"],True)
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        unsafe=cmd[:]
        unsafe[unsafe.index("--output")+1]=str(self.db)
        self.assertNotEqual(subprocess.run(unsafe,capture_output=True).returncode,0)
        self.assertEqual(report(self.db,at=T1)["shown"],2)


if __name__=="__main__":
    unittest.main()
