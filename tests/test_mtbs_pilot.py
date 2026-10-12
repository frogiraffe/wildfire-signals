"""Provider-shaped MTBS government ArcGIS unit tests (NOT real USGS data)."""
from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path

from fire_public.mtbs_pilot import (
    BASE, YEARS, _parse_feature, _schema, compare_archived_nifc,
    save_sample, source_sample,
)
from test_official_lead_refresh import LeadLiveAuditTests


def stamp(year):
    return int(datetime(year,7,20,tzinfo=timezone.utc).timestamp()*1000)


def entry(year,oid,*,name=None):
    return {
        "attributes":{
            "objectid":oid,"fire_id":f"TEST_{year}_{oid}",
            "fire_name":name if name is not None else f"Example {oid}",
            "fire_type":"Wildfire" if oid%2 else "Prescribed Fire",
            "ig_date":stamp(year),
            "acres":1000.0+oid,
        },
        "geometry":{"x":-120.0 + oid*0.002,
                    "y":37.46 + oid*0.002},
    }


class USFSFixture:
    def __init__(self):
        self.calls=[]
        self.corrupt=None
        self.changed_source=False

    def __call__(self,url,params):
        self.calls.append((url,params.copy()))
        year=2017 if f"/{YEARS[2017]}" in url else 2018
        if url.endswith("/query"):
            if params.get("returnIdsOnly")=="true":
                result={"objectIdFieldName":"objectid",
                        "objectIds":[1,2,3,4,5,6,7,8,9,10]}
            else:
                ids=[int(i) for i in params["objectIds"].split(",")]
                rows=[entry(year,k) for k in ids]
                if self.corrupt=="missing":rows.pop()
                if self.corrupt=="year":
                    rows[0]["attributes"]["ig_date"]=stamp(year-1)
                if self.corrupt=="geometry":
                    rows[0]["geometry"]["x"]=370.0
                if self.corrupt=="duplicate":
                    rows[-1]["attributes"]["objectid"]=rows[0]["attributes"]["objectid"]
                result={"features":rows,"spatialReference":{"wkid":4326}}
        else:
            result={
                "id":YEARS[year],
                "name":f"{year} Fire Occurrence Locations",
                "geometryType":"esriGeometryPoint",
                "capabilities":"Map,Query,Data",
                "supportedQueryFormats":"JSON, geoJSON",
                "fields":[{"name":f,"type":"esriFieldTypeString"}
                          for f in ("objectid","fire_id","fire_name","fire_type",
                                    "ig_date","acres")],
                "maxRecordCount":2000,
            }
            if self.corrupt=="schema":
                result["id"]=999
        raw=json.dumps(result,ensure_ascii=False).encode()
        return result,raw


class MTBSRealTransportFixtureTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.service=USFSFixture()

    def sample(self,**kwargs):
        return source_sample(years=[2018,2017],
                             sample_per_year=4,seed="real-repro-fixture",
                             get=self.service,clock=lambda:"2026-10-13T12:00:00Z",
                             **kwargs)

    def test_two_year_source_sample_original_bytes_and_fire_type(self):
        report,raw=self.sample()
        self.assertEqual(report["years"],[2017,2018])
        self.assertEqual(len(report["points"]),8)
        self.assertEqual(len(raw),6)
        self.assertTrue(all("mtbs-" in name for name in raw))
        self.assertEqual(len(self.service.calls),6)
        self.assertEqual(report["source_transport"],"injected_test_transport")
        self.assertEqual(report["negative_fire_labels_created"],0)
        self.assertFalse(report["outcome_independence_established"])
        self.assertEqual({x["source_fire_type"] for x in report["points"]},
                         {"Wildfire","Prescribed Fire"})
        first=report["source_years"][0]
        self.assertEqual(first["year"],2017)
        self.assertEqual(first["source_ids_total"],10)
        self.assertEqual(first["sampled_points"],4)
        for x in first["raw_source_files"]:
            self.assertEqual(hashlib.sha256(raw[x["filename"]]).hexdigest(),x["sha256"])
        self.assertTrue(all(x["source_ignition_at"] and
                            x["source_ignition_at"].startswith(str(x["fire_year_layer"]))
                            for x in report["points"]))

    def test_seeded_selection_reproducible(self):
        first,_=self.sample()
        selected=[(x["fire_year_layer"],x["object_id"]) for x in first["points"]]
        second,_=self.sample()
        self.assertEqual(selected,[(x["fire_year_layer"],x["object_id"])
                                   for x in second["points"]])
        different,_=source_sample(years=[2017,2018],sample_per_year=4,
                                  seed="another-seed",get=self.service,
                                  clock=lambda:"2026-10-13T12:00:00Z")
        self.assertNotEqual(selected,[(x["fire_year_layer"],x["object_id"])
                                      for x in different["points"]])

    def test_schema_drift_and_incomplete_government_response_fail(self):
        for error,expected in [
                ("schema","layer or fields"),
                ("missing","incomplete source"),
                ("year","ignition date conflicts"),
                ("geometry","WGS84 point"),
                ("duplicate","point IDs do not match")]:
            with self.subTest(error=error):
                self.service.corrupt=error
                with self.assertRaisesRegex(ValueError,expected):
                    self.sample()
        self.service.corrupt=None

    def test_invalid_params_reject_before_network(self):
        for args in [
            {"years":[2016]}, {"years":[2018,2018]},
            {"years":[2017,2018,2019]}, {"years":[]},
            {"years":[2017],"sample_per_year":21},
            {"years":[2017],"sample_per_year":0}
        ]:
            with self.assertRaises(ValueError):
                source_sample(get=self.service,**args)
        self.assertEqual(self.service.calls,[])

    def test_snapshot_new_only_and_checksum_stability(self):
        report,raw=self.sample()
        folder=self.root/"mtbs-real-source-shape"
        save_sample(folder,report,raw)
        self.assertEqual(len(list(folder.iterdir())),7)
        self.assertEqual(json.loads((folder/"sample-summary.json").read_text())
                         ["sampled_source_points"],8)
        for name,data in raw.items():
            self.assertEqual((folder/name).read_bytes(),data)
        with self.assertRaisesRegex(ValueError,"must be new"):
            save_sample(folder,report,raw)
        self.assertEqual(len(list(folder.iterdir())),7)

    def test_conservative_possible_co_location_never_establishes_identity(self):
        fixture=LeadLiveAuditTests("test_reconcile_original_real_archive_exact_ids_and_bytes")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        report,raw=self.sample()
        result=compare_archived_nifc(report,fixture.db,nifc_at=fixture.queue["as_of"])
        self.assertEqual(result["mtbs_sampled_source_points"],8)
        self.assertEqual(result["nifc_sampled_source_polygons"],4)
        self.assertGreater(len(result["spatial_co_location_candidates"]),0)
        self.assertTrue(all(not x["same_incident_confirmed"] for x in
                            result["spatial_co_location_candidates"]))
        self.assertEqual(result["matching_scientific_status"],
                         "proximity_only_not_event_identity")
        self.assertFalse(result["nonmatches_count_as_absent_fires"])
        self.assertEqual(result["negative_fire_labels_created"],0)


if __name__=="__main__":
    unittest.main()
