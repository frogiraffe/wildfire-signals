"""Mock HTTP transport tests for SAME region/year NIFC + MTBS ArcGIS research.

All provider responses here are synthetic; live source verification is a
separate CI job against two independently maintained actual government APIs.
"""
from __future__ import annotations
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fire_public.mtbs_region_study import (
    aligned_capture, roi_bbox, write_capture,
)
from test_official_lead_refresh import metadata
from test_mtbs_pilot import stamp


ROI=[-121.0,36.0,-119.0,38.0]
YEAR=2018


def nifc_polygon(oid,inside=True):
    x=-120.05 if inside else -100
    return {
        "type":"Feature",
        "properties":{
            "OBJECTID":oid,"GlobalID":f"guid-{YEAR}-{oid}",
            "FIRE_YEAR_INT":YEAR,"INCIDENT":f"Fire record {oid}",
            "GIS_ACRES":800.0,"SOURCE":"agency",
        },
        "geometry":{"type":"Polygon","coordinates":[[
            [x,37],[x+.2,37],[x+.2,37.2],[x,37.2],[x,37],
        ]]},
    }


def mtbs_point(oid,inside=True):
    return {
        "attributes":{"objectid":oid,"fire_id":f"TEST_FIRE_{oid}",
            "fire_name":f"Fire record {oid}","fire_type":"Wildfire",
            "ig_date":stamp(YEAR),"acres":1400.0},
        "geometry":{"x":-120.0 if inside else -100,"y":37.1},
    }


class RegionServer:
    def __init__(self):
        self.nifc_calls=[]
        self.mtbs_calls=[]
        self.nifc_ids=[1,2,3]
        self.mtbs_ids=[100,101]
        self.missing=None
        self.outside=None
    def nifc(self,params):
        self.nifc_calls.append(params.copy())
        if params.get("returnIdsOnly")=="true":
            data={"objectIdFieldName":"OBJECTID","objectIds":self.nifc_ids}
        else:
            chosen=[int(x) for x in params["objectIds"].split(",")]
            features=[nifc_polygon(x,not self.outside=="nifc") for x in chosen]
            if self.missing=="nifc":features.pop()
            data={"type":"FeatureCollection","features":features}
        return json.dumps(data,sort_keys=True).encode()
    def mtbs(self,url,params):
        self.mtbs_calls.append((url,params.copy()))
        if not url.endswith("/query"):
            data={
                "id":70,"name":"2018 Fire Occurrence Locations",
                "geometryType":"esriGeometryPoint","capabilities":"Map,Query,Data",
                "supportedQueryFormats":"JSON, geoJSON",
                "fields":[{"name":x,"type":"esriFieldTypeString"} for x in (
                    "objectid","fire_id","fire_name","fire_type","ig_date","acres")],
            }
        elif params.get("returnIdsOnly")=="true":
            data={"objectIdFieldName":"objectid","objectIds":self.mtbs_ids}
        else:
            chosen=[int(x) for x in params["objectIds"].split(",")]
            features=[mtbs_point(x,not self.outside=="mtbs") for x in chosen]
            if self.missing=="mtbs":features.pop()
            data={"features":features,"spatialReference":{"wkid":4326}}
        encoded=json.dumps(data,sort_keys=True).encode()
        return data,encoded


class SharedRegionStudyTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup)
        self.root=Path(d.name)
        self.provider=RegionServer()

    def study(self,**overrides):
        options=dict(year=YEAR,roi=ROI,limit_per_source=10,
            radius_km=15,seed="fixture-same-place",
            nifc_get=self.provider.nifc,mtbs_get=self.provider.mtbs,
            nifc_metadata=metadata,clock=lambda:"2026-10-13T12:00:00Z")
        options.update(overrides)
        return aligned_capture(**options)

    def test_queries_use_identical_region_and_year_before_selection(self):
        study,raws=self.study()
        self.assertEqual(len(study["nifc_polygons"]),3)
        self.assertEqual(len(study["mtbs_points"]),2)
        self.assertGreater(len(study["candidate_pairs"]),0)
        self.assertTrue(all(p["within_study_search_radius_only"] and
                            p["same_event_verified"] is False for p in study["candidate_pairs"]))
        self.assertTrue(all(p["independent_outcome_verified"] is False
                            for p in study["candidate_pairs"]))
        self.assertEqual(study["negative_labels_created"],0)
        self.assertFalse(study["forecast_model_skill_measured"])
        self.assertEqual(study["nifc_transport"],"injected_test_transport")
        self.assertEqual(study["mtbs_transport"],"injected_test_transport")
        self.assertEqual(study["source_population"]["nifc_roi_object_ids"],3)
        self.assertEqual(study["source_population"]["mtbs_roi_object_ids"],2)
        self.assertTrue(study["source_population"]["both_selected_records_exhaust_all_source_roi_ids"])
        nifc_lookup=self.provider.nifc_calls[0]
        mtbs_lookup=self.provider.mtbs_calls[1][1]
        for params in (nifc_lookup,mtbs_lookup):
            self.assertEqual(params["geometryType"],"esriGeometryEnvelope")
            self.assertEqual(params["spatialRel"],"esriSpatialRelIntersects")
            self.assertEqual(params["inSR"],"4326")
            self.assertEqual(params["geometry"],"-121.0,36.0,-119.0,38.0")
            self.assertEqual(params["returnIdsOnly"],"true")
        self.assertEqual(nifc_lookup["where"],"FIRE_YEAR_INT = 2018")
        self.assertEqual(mtbs_lookup["where"],"1=1")
        self.assertEqual(len(raws),5)
        self.assertEqual(len(study["raw_source_files"]),len(raws))
        for f in study["raw_source_files"]:
            self.assertEqual(f["sha256"],hashlib.sha256(raws[f["filename"]]).hexdigest())

    def test_source_hash_determinism_and_bounded_id_subsets(self):
        one,raw=self.study(limit_per_source=2)
        two,_=self.study(limit_per_source=2)
        self.assertEqual([x["object_id"] for x in one["nifc_polygons"]],
                         [x["object_id"] for x in two["nifc_polygons"]])
        self.assertEqual(one["source_population"]["nifc_roi_object_ids"],3)
        self.assertEqual(one["source_population"]["mtbs_roi_object_ids"],2)
        self.assertFalse(one["source_population"]["both_selected_records_exhaust_all_source_roi_ids"])

    def test_missing_ids_fail_closed_and_do_not_create_negative(self):
        for which in ("nifc","mtbs"):
            with self.subTest(provider=which):
                self.provider.missing=which
                with self.assertRaisesRegex(ValueError,"incomplete"):
                    self.study()
        self.provider.missing=None

    def test_unrelated_source_geometry_refused(self):
        for which in ("nifc","mtbs"):
            with self.subTest(provider=which):
                self.provider.outside=which
                with self.assertRaisesRegex(ValueError,"outside requested ROI"):
                    self.study()
        self.provider.outside=None

    def test_bad_roi_and_excess_budget_rejected_before_http(self):
        for roi in ([-120,40,-121,41],[-180,-90,180,90],
                    [179,39,-179,40],[float("nan"),39,-120,40]):
            with self.assertRaises(ValueError):
                self.study(roi=roi)
        for value in (0,41,True):
            with self.assertRaises(ValueError):
                self.study(limit_per_source=value)
        for radius in (0,51,float("nan")):
            with self.assertRaises(ValueError):
                self.study(radius_km=radius)
        self.assertFalse(self.provider.nifc_calls)
        self.assertFalse(self.provider.mtbs_calls)

    def test_no_roi_ids_fails_unknown_not_no_fire(self):
        self.provider.mtbs_ids=[]
        with self.assertRaisesRegex(ValueError,"empty"):
            self.study()
        self.provider.mtbs_ids=[100,101]

    def test_stable_evidence_file_export_and_existing_path_guard(self):
        report,raws=self.study()
        output=self.root/"aligned"
        write_capture(output,report,raws)
        self.assertEqual(len(list(output.iterdir())),len(raws)+1)
        self.assertEqual(json.loads((output/"aligned-study.json").read_text())
                         ["source_population"]["mtbs_roi_object_ids"],2)
        for item in report["raw_source_files"]:
            self.assertEqual((output/item["filename"]).read_bytes(),raws[item["filename"]])
        with self.assertRaisesRegex(ValueError,"new research output directory"):
            write_capture(output,report,raws)

    def test_prescribed_fire_flag_remains_distinct(self):
        data,raw=self.study()
        self.assertEqual(data["mtbs_points"][0]["source_fire_type"],"Wildfire")
        self.assertFalse(data["mtbs_points"][0]["is_independent_nonfire_label"])


if __name__=="__main__":
    unittest.main()
