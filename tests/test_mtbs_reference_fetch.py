"""Offline fake transport around *real* official ArcGIS query/metadata pipeline.

The tests exercise actual validated GeoJSON, provenance SHA, pagination,
geographic splits and CLI input integrity without paid API or fake accuracy.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs

from fire_public.mtbs_reference_fetch import (
    OFFICIAL_LAYER,_query,_bounds,collect_mtbs,save_mtbs,_NoRedirect)
from fire_public.perimeter_benchmark import load_reference

TEST_TIME="2026-10-12T18:00:00+00:00"


def feature(index, lon=-110.0):
    return {"type":"Feature","properties":{
        "OBJECTID":index,"FIRE_ID":f"MTBS-{index:04d}",
        "FIRE_NAME":f"Reference {index}","FIRE_TYPE":"Wildfire",
        "IG_DATE":int(datetime(2024,8,1,tzinfo=timezone.utc).timestamp()*1000),
        "YEAR":2024,
        "STARTMONTH":8,"STARTDAY":1},
        "geometry":{"type":"Polygon","coordinates":[
            [[lon-0.1,40],[lon+0.1,40],[lon+0.1,40.2],[lon-0.1,40.2],
             [lon-0.1,40]]]}}
 

class FakeMtbsTransport:
    def __init__(self,features,limit_override=None):
        self.items=features
        self.calls=[]
        self.limit_override=limit_override
    def __call__(self,url):
        assert url.startswith(OFFICIAL_LAYER+"/query?")
        self.calls.append(url)
        q=parse_qs(urlparse(url).query)
        start=int(q["resultOffset"][0])
        count=int(q["resultRecordCount"][0])
        if self.limit_override is not None:
            count=min(count,self.limit_override)
        if "geometry" in q:
            west,south,east,north=map(float,q["geometry"][0].split(","))
            found=[x for x in self.items if
                   west<=x["geometry"]["coordinates"][0][0][0]<=east]
        else:
            found=self.items
        chunk=found[start:start+count]
        return json.dumps({"type":"FeatureCollection","features":chunk}).encode()


class MtbsAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.geo=self.root/"mtbs.geojson"
        self.meta=self.root/"mtbs-metadata.json"

    def test_official_multipage_download_validated_and_checksum_persisted(self):
        transport=FakeMtbsTransport([feature(i) for i in range(101)])
        manifest=save_mtbs(self.geo,self.meta,year=2024,max_features=120,
                           fetch=transport,retrieved_at=TEST_TIME)
        self.assertEqual(manifest["page_count"],2)
        self.assertEqual(manifest["feature_count"],101)
        self.assertEqual(len(transport.calls),2)
        self.assertEqual(manifest["geojson_sha256"],
                         hashlib.sha256(self.geo.read_bytes()).hexdigest())
        loaded=load_reference(self.geo,source_url=OFFICIAL_LAYER,
                              published_at=manifest["retrieved_at"])
        self.assertEqual(loaded["included_wildfire_features"],101)
        self.assertFalse(loaded["source_authenticity_verified"])
        self.assertFalse(manifest["source_publication_date_independently_verified"])
        self.assertEqual(json.loads(self.meta.read_text())["feature_count"],101)

    def test_global_date_line_bbox_queries_are_split_and_deduped(self):
        left=feature(1,lon=179.8)
        right=feature(2,lon=-179.8)
        # Wide polygons are included by mock coordinate not full server envelope.
        t=FakeMtbsTransport([left,right])
        geo,meta=collect_mtbs(year=2024,bbox=(179,-10,-179,70),fetch=t,
                              retrieved_at=TEST_TIME)
        self.assertEqual(len(geo["features"]),2)
        self.assertEqual(len(t.calls),2)
        self.assertEqual(meta["requested_bbox"],[179,-10,-179,70])
        q=[parse_qs(urlparse(url).query) for url in t.calls]
        self.assertTrue(all(x["inSR"]==["4326"] and x["outSR"]==["4326"] for x in q))
        self.assertEqual(_bounds([179,-10,-179,70]),[
            (179.,-10.,180.,70.),(-180.,-10.,-179.,70.)])

    def test_missing_or_truncated_server_results_cannot_publish_partial_reference(self):
        t=FakeMtbsTransport([feature(i) for i in range(104)])
        with self.assertRaisesRegex(ValueError,"max_features"):
            save_mtbs(self.geo,self.meta,year=2024,max_features=100,
                      fetch=t,retrieved_at=TEST_TIME)
        self.assertFalse(self.geo.exists())
        self.assertFalse(self.meta.exists())
        bad=lambda url:json.dumps({"error":{"message":"Not available"}}).encode()
        with self.assertRaisesRegex(ValueError,"FeatureCollection"):
            save_mtbs(self.geo,self.meta,year=2024,fetch=bad,
                      retrieved_at=TEST_TIME)
        self.assertFalse(self.geo.exists())

    def test_corrupt_duplicate_identity_and_invalid_polygons_rejected(self):
        a=feature(1)
        b=feature(1,lon=-120)
        conflicting=FakeMtbsTransport([a,b])
        with self.assertRaisesRegex(ValueError,"conflicting"):
            save_mtbs(self.geo,self.meta,year=2024,fetch=conflicting,
                      retrieved_at=TEST_TIME)
        broken=feature(1)
        broken["geometry"]["coordinates"]=[[[200,0],[1,0],[1,1],[200,0]]]
        with self.assertRaisesRegex(ValueError,"lon/lat"):
            save_mtbs(self.geo,self.meta,year=2024,fetch=FakeMtbsTransport([broken]),
                      retrieved_at=TEST_TIME)
        self.assertFalse(self.geo.exists())

    def test_no_trust_in_redirects_and_strict_filter_urls(self):
        url=_query(2024,None,0)
        self.assertTrue(url.startswith(OFFICIAL_LAYER+"/query?"))
        query=parse_qs(urlparse(url).query)
        self.assertEqual(query["where"],["YEAR = 2024 AND FIRE_TYPE = 'Wildfire'"])
        self.assertEqual(query["f"],["geojson"])
        self.assertEqual(query["orderByFields"],["OBJECTID ASC"])
        with self.assertRaisesRegex(ValueError,"redirect"):
            _NoRedirect().redirect_request(None,None,302,"redirect",{},
                                          "https://evil.invalid/path")
        with self.assertRaises(ValueError):
            _bounds((0,2,0,3))
        with self.assertRaises(ValueError):
            _bounds((0,91,2,93))

    def test_manifest_integrity_verifies_reference_through_real_cli(self):
        manifest=save_mtbs(self.geo,self.meta,year=2024,
                           fetch=FakeMtbsTransport([feature(1)]),
                           retrieved_at=TEST_TIME)
        # The corresponding current FIRMS archive may be empty, which is
        # valid and not a fire-negative label.
        from fire_public.pixel_history import _create_tables
        import sqlite3
        db=self.root/"pixels.db"
        with sqlite3.connect(db) as connection:
            _create_tables(connection)
        from fire_public.perimeter_benchmark import benchmark_perimeters
        loaded=load_reference(self.geo,source_url=manifest["source_url"],
                              published_at=manifest["retrieved_at"])
        report=benchmark_perimeters(db,loaded,as_of="2026-10-14T18:00:00Z",observation_days=14)
        self.assertEqual(report["valid_negative_labels_created"],0)
        self.assertEqual(report["with_any_eligible_collector_receipts"],0)
        args=[sys.executable,"-m","fire_public.perimeter_benchmark",
              "--pixel-db",str(db),"--geojson",str(self.geo),
              "--reference-manifest",str(self.meta),
              "--as-of","2026-10-14T18:00:00Z","--observation-days","14",
              "--json",str(self.root/"comparison.json")]
        completed=subprocess.run(args,text=True,capture_output=True)
        self.assertEqual(completed.returncode,0,completed.stderr)
        result=json.loads((self.root/"comparison.json").read_text())
        self.assertEqual(result["evaluated_reference_perimeters"],1)
        # Corrupt downloaded reference after downloading; must fail closed.
        self.geo.write_bytes(self.geo.read_bytes()+b" ")
        corrupt=subprocess.run(args,text=True,capture_output=True)
        self.assertNotEqual(corrupt.returncode,0)
        self.assertIn("does not match",corrupt.stderr)

    def test_missing_outputs_and_invalid_request_budget_refused(self):
        with self.assertRaises(ValueError):
            collect_mtbs(year=2024,max_features=0,
                         fetch=FakeMtbsTransport([]),retrieved_at=TEST_TIME)
        with self.assertRaises(ValueError):
            collect_mtbs(year=1980,fetch=FakeMtbsTransport([]),
                         retrieved_at=TEST_TIME)
        self.geo.write_text("owned")
        with self.assertRaises(FileExistsError):
            save_mtbs(self.geo,self.meta,year=2024,
                      fetch=FakeMtbsTransport([]),retrieved_at=TEST_TIME)
        self.assertEqual(self.geo.read_text(),"owned")

if __name__=="__main__":
    unittest.main()
