"""Live service contract checks use provider-shaped fixtures, no network in tests."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.official_live_probe import (
    EXPECTED_ITEM_ID, live_sample_probe, validate_layer_metadata,
)
from fire_public.official_perimeters import report

T="2026-10-13T14:00:00Z"


def layer_metadata():
    return {
        "id":0,"serviceItemId":EXPECTED_ITEM_ID,
        "geometryType":"esriGeometryPolygon","objectIdField":"OBJECTID",
        "globalIdField":"GlobalID","supportedQueryFormats":"JSON, geoJSON, PBF",
        "capabilities":"Query,Extract","maxRecordCount":2000,
        "editingInfo":{"dataLastEditDate":1782422738160},
        "fields":[{"name":n,"type":"esriFieldTypeString"}
                  for n in ("OBJECTID","GlobalID","FIRE_YEAR_INT",
                            "INCIDENT","GIS_ACRES","SOURCE")],
    }


class StubProvider:
    def __init__(self):
        self.calls=[]

    def __call__(self, args):
        self.calls.append(dict(args))
        if args.get("returnIdsOnly")=="true":
            return {"objectIdFieldName":"OBJECTID","objectIds":[4,5]}
        coords=[[[-120.02,37],[-119.98,37],[-119.98,37.03],
                 [-120.02,37.03],[-120.02,37]]]
        return {"type":"FeatureCollection","features":[{
            "type":"Feature",
            "properties":{"OBJECTID":4,"GlobalID":"{perimeter-guid-4}",
                          "FIRE_YEAR_INT":2018,"GIS_ACRES":99.0,
                          "INCIDENT":"Official example","SOURCE":"USFS"},
            "geometry":{"type":"Polygon","coordinates":coords},
        }]}


class NifcLiveProbeTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root=Path(d.name)
        self.db=self.root/"nifc.sqlite3"
        self.remote=StubProvider()

    def probe(self):
        return live_sample_probe(self.db,year=2018,clock=lambda:T,
            fetch_metadata=layer_metadata,get_json=self.remote)

    def test_real_http_contract_schema_and_one_saved_polygon(self):
        result=self.probe()
        self.assertEqual(result["status"],"live_provider_contract_verified")
        self.assertEqual(result["verified_retrieved_records"],1)
        self.assertTrue(all(result["source_metadata"]["assertions"].values()))
        self.assertEqual(result["source_metadata"]["query_max_record_count"],2000)
        self.assertEqual(result["retrieval"]["total_source_ids"],2)
        self.assertTrue(result["retrieval"]["subset_only"])
        self.assertEqual(result["stored_feature"]["object_id"],4)
        self.assertEqual(result["stored_feature"]["fire_year"],2018)
        self.assertEqual(result["stored_feature"]["geometry_type"],"Polygon")
        self.assertEqual(result["negative_labels_created"],0)
        self.assertFalse(result["model_ready"])
        self.assertEqual(report(self.db,at=T)["shown"],1)
        self.assertEqual(len(self.remote.calls),2)
        self.assertEqual(self.remote.calls[0]["where"],"FIRE_YEAR_INT = 2018")
        self.assertEqual(self.remote.calls[1]["objectIds"],"4")

    def test_missing_or_wrong_provider_fields_fail_before_network(self):
        for field,wrong in [
            ("geometryType","esriGeometryPoint"),
            ("objectIdField","FID"),
            ("serviceItemId","wrong"),
            ("supportedQueryFormats","JSON"),
            ("capabilities","Edit"),
        ]:
            with self.subTest(field=field):
                metadata=layer_metadata()
                metadata[field]=wrong
                with self.assertRaisesRegex(ValueError,"contract drift"):
                    validate_layer_metadata(metadata)
        for missing in ("FIRE_YEAR_INT","GlobalID"):
            metadata=layer_metadata()
            metadata["fields"]=[v for v in metadata["fields"] if v["name"]!=missing]
            with self.assertRaisesRegex(ValueError,"source_fields_present"):
                validate_layer_metadata(metadata)

    def test_invalid_or_empty_polygon_response_does_not_prove_fires_absent(self):
        def missing(args):
            if args.get("returnIdsOnly")=="true":
                return {"objectIds":[]}
            raise AssertionError("unexpected geometry request")
        with self.assertRaisesRegex(ValueError,"no sample perimeter"):
            live_sample_probe(self.db,year=2018,clock=lambda:T,
                              fetch_metadata=layer_metadata,get_json=missing)
        self.assertTrue(self.db.exists())
        self.assertEqual(report(self.db,at=T)["shown"],0)

    def test_metadata_raw_bytes_are_not_copied_into_report(self):
        doc=layer_metadata()
        doc["sensitive_provider_unrelated_blob"]="hidden field should not be exported"
        result=validate_layer_metadata(doc)
        self.assertNotIn("hidden field",json.dumps(result))
        self.assertEqual(len(result["schema_sha256"]),64)

    def test_multiple_calls_same_capture_time_do_not_duplicate(self):
        self.probe()
        self.probe()
        self.assertEqual(report(self.db,at=T)["shown"],1)


if __name__=="__main__":
    unittest.main()
