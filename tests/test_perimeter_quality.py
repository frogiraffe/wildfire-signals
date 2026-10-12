"""Offline, authentic-format NIFC polygon quality pipeline regression tests."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.official_perimeters import sync_year
from fire_public.perimeter_quality import (
    _lon_span, _ring_degenerate, audit_quality, render_quality_html,
)

NOW="2026-10-13T00:00:00Z"


def geo(oid, year, *, source="USFS", acres=11.0, name="Agency polygon",
        longitude=None, degenerate=False, include_guid=True):
    if longitude is None:
        longitude = -120.0 + oid * 0.12
    outer=[[longitude,37.0],[longitude+0.02,37.0],
           [longitude+0.02,37.02],[longitude,37.02],[longitude,37.0]]
    if degenerate:
        outer=[[longitude,37.0]]*4
    props={"OBJECTID":oid,"FIRE_YEAR_INT":year,
           "INCIDENT":name,"GIS_ACRES":acres,"SOURCE":source}
    if include_guid:
        props["GlobalID"]=f"{{id-{year}-{oid}}}"
    return {"type":"Feature","properties":props,
            "geometry":{"type":"Polygon","coordinates":[outer]}}


class OfficialService:
    def __init__(self):
        self.features={
            2017:[
                geo(1,2017),
                geo(2,2017,name="<script>alert(1)</script>",source=None,
                    acres=0.0,degenerate=True),
                geo(3,2017,name="",acres=None,include_guid=False),
            ],
            2018:[
                geo(4,2018),
                geo(5,2018,source="USFS",acres=12.0),
            ],
        }
        self.year=None
    def __call__(self,params):
        if "where" in params:
            self.year=int(params["where"].split("=")[-1])
            return {"objectIds":[r["properties"]["OBJECTID"] for r in
                                 self.features[self.year]]}
        ids={int(v) for v in params["objectIds"].split(",")}
        return {"type":"FeatureCollection","features":[r for r in
                self.features[self.year] if r["properties"]["OBJECTID"] in ids]}


class OfficialQualityTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root=Path(d.name)
        self.db=self.root/"ifph.sqlite3"
        self.api=OfficialService()
        for year in (2017,2018):
            sync_year(self.db,year=year,max_records=3,
                      get_json=self.api,clock=lambda:NOW,
                      selection_mode="hash",selection_seed="quality-fixture")

    def audit(self,years=None,at=NOW):
        return audit_quality(self.db,at=at,years=years or [2017,2018])

    def test_year_denominators_and_explicit_missingness(self):
        r=self.audit()
        self.assertEqual(r["sampled_polygons_total"],5)
        self.assertEqual([y["sampled_record_count"] for y in r["year_quality"]],[3,2])
        first=r["year_quality"][0]
        self.assertEqual(first["field_presence"]["GlobalID"]["nonempty_sampled_records"],2)
        self.assertEqual(first["field_presence"]["INCIDENT"]["nonempty_sampled_records"],2)
        self.assertEqual(first["field_presence"]["SOURCE"]["nonempty_sampled_records"],2)
        self.assertEqual(first["field_presence"]["GIS_ACRES"]["nonempty_sampled_records"],2)
        self.assertEqual(first["field_presence"]["GlobalID"]["sample_fraction"],0.6667)
        self.assertEqual(first["flags_by_type"]["degenerate_coordinate_ring"],1)
        self.assertEqual(first["flags_by_type"]["nonpositive_reported_acres"],1)
        self.assertEqual(first["flags_by_type"]["missing_reported_acres"],1)
        self.assertEqual(r["source_coverage_status"],"not_a_verified_complete_fire_census")
        self.assertEqual(r["negative_labels_created"],0)
        self.assertFalse(r["negative_sampling_readiness"]["training_ready"])
        self.assertFalse(r["forecast_skill_measured"])

    def test_uncaptured_year_is_unknown_not_zero_fires(self):
        r=self.audit(at="2020-01-01T00:00:00Z")
        self.assertEqual(r["sampled_polygons_total"],0)
        self.assertEqual(r["uncaptured_years"],[2017,2018])
        self.assertTrue(all(y["published_source_id_count"] is None for y in r["year_quality"]))
        self.assertTrue(all(y["field_presence"]["GIS_ACRES"]["sample_fraction"] is None
            for y in r["year_quality"]))

    def test_exact_duplicate_polygon_geometry_is_review_only(self):
        self.api.features[2018][1]["geometry"]=json.loads(json.dumps(
            self.api.features[2018][0]["geometry"]))
        sync_year(self.db,year=2018,max_records=3,
            get_json=self.api,clock=lambda:"2026-10-14T00:00:00Z",
            selection_mode="hash",selection_seed="quality-fixture")
        r=self.audit(at="2026-10-14T00:00:00Z")
        dupe=r["exact_duplicate_polygon_groups"]
        self.assertEqual(len(dupe),1)
        self.assertEqual(dupe[0]["distinct_source_records"],2)
        self.assertTrue(r["negative_sampling_readiness"]["training_ready"] is False)

    def test_source_hash_integrity_refuses_tampered_sqlite(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("""UPDATE perimeter_versions SET attributes_json=?
              WHERE object_id=1""",(json.dumps({"OBJECTID":1,"FIRE_YEAR_INT":2017}),))
        with self.assertRaisesRegex(ValueError,"SHA-256|source manifest"):
            self.audit()

    def test_html_escapes_incident_names(self):
        result=self.audit()
        exported=render_quality_html(result)
        self.assertIn("NIFC official source sample quality",exported)
        self.assertNotIn("<script>alert(1)</script>",exported)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;",exported)
        self.assertIn("Independent negative sampling ready: <strong>No</strong>",exported)

    def test_column_span_and_degenerate_coordinate_rules(self):
        width, wrapped=_lon_span([179.9,-179.9,179.9,-179.9])
        self.assertAlmostEqual(width,0.2,places=5)
        self.assertTrue(wrapped)
        self.assertEqual(_lon_span([0.0]*5),(0.0,False))
        self.assertTrue(_ring_degenerate([[10,1],[10,1],[10,1],[10,1]]))
        self.assertFalse(_ring_degenerate([[-120,37],[-119.99,37],
            [-119.99,37.01],[-120,37.01],[-120,37]]))

    def test_cli_exports_real_source_shape_and_prevents_overwrite(self):
        output=self.root/"quality.json"
        website=self.root/"quality.html"
        cmd=[sys.executable,"-m","fire_public.perimeter_quality",
             "--db",str(self.db),"--at",NOW,"--year","2017","--year","2018",
             "--json",str(output),"--html",str(website)]
        done=subprocess.run(cmd,capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr)
        self.assertEqual(json.loads(output.read_text())["sampled_polygons_total"],5)
        self.assertEqual(json.loads(done.stdout)["negative_labels_created"],0)
        self.assertIn("Independent negative sampling ready",website.read_text())
        self.assertNotEqual(subprocess.run(cmd,capture_output=True).returncode,0)
        unsafe=cmd[:]
        unsafe[unsafe.index("--json")+1]=str(self.db)
        self.assertNotEqual(subprocess.run(unsafe,capture_output=True).returncode,0)
        self.assertEqual(self.audit()["sampled_polygons_total"],5)


if __name__=="__main__":
    unittest.main()
