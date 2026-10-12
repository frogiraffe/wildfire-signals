"""Source reconciliation uses real importer SQLite with synthetic HTTP fixtures.

No test-generated perimeter is represented as independently verified
wildfire/nonfire ground truth or a successful live HTTPS network request.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fire_public.official_perimeters import SERVICE, sync_year
from fire_public.official_lead_refresh import verify_leads, write_evidence
from fire_public.label_review import prepare_queue
from fire_public.official_live_probe import EXPECTED_ITEM_ID

OLD="2026-10-12T12:00:00Z"
NEW="2026-10-13T12:00:00Z"


def feature(oid, year, *, name=None, guid=None):
    lat=37.0 + (oid % 20)*0.04
    lon=-120.0
    return {"type":"Feature", "properties":{
        "OBJECTID":oid, "GlobalID":guid or f"guid-{year}-{oid}",
        "FIRE_YEAR_INT":year, "INCIDENT":name or f"2018 agency context {oid}",
        "GIS_ACRES":float(oid+3), "SOURCE":"USFS",
    }, "geometry":{"type":"Polygon","coordinates":[[
        [lon,lat],[lon+0.02,lat],[lon+0.02,lat+0.02],
        [lon,lat+0.02],[lon,lat],
    ]]}}


def metadata():
    return {
        "id":0,"serviceItemId":EXPECTED_ITEM_ID,
        "geometryType":"esriGeometryPolygon",
        "objectIdField":"OBJECTID","globalIdField":"GlobalID",
        "supportedQueryFormats":"JSON,geoJSON",
        "capabilities":"Query","maxRecordCount":2000,
        "fields":[{"name":k,"type":"esriFieldTypeString"} for k in
                  ("OBJECTID","GlobalID","FIRE_YEAR_INT","INCIDENT","GIS_ACRES")],
    }


class Provider:
    def __init__(self):
        self.year=2017
        self.ids={2017:[11,12],2018:[21,22]}
        self.revised=False
        self.omit=False
        self.wrong_identity=False
        self.requests=[]

    def original(self,p):
        if "where" in p:
            self.year=int(p["where"].split("=")[-1])
            return {"objectIds":self.ids[self.year]}
        return {"type":"FeatureCollection","features":[
            feature(int(i),self.year) for i in p["objectIds"].split(",")]}

    def page(self,p):
        self.requests.append(p)
        ids=[int(i) for i in p["objectIds"].split(",")]
        # Our sampled test IDs are distinct across years.
        year=2017 if all(i in self.ids[2017] for i in ids) else 2018
        output=[feature(i,year,
                name=("Corrected source attribute" if self.revised and i==11 else None),
                guid=("changed-global-id" if self.wrong_identity and i==11 else None))
                for i in ids]
        if self.omit:
            output.pop()
        return json.dumps({"type":"FeatureCollection",
            "features":output},ensure_ascii=False,separators=(",",":")).encode()


class LeadLiveAuditTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.db=self.root/"ifph.sqlite3"
        self.queue_path=self.root/"review-queue.json"
        self.provider=Provider()
        for year in (2017,2018):
            sync_year(self.db,year=year,max_records=2,
                get_json=self.provider.original,
                clock=lambda:OLD,selection_mode="hash",
                selection_seed="lead-test")
        frame={"schema_version":1,
            "frame_name":"Fixture-only independent frame candidates",
            "sampling_protocol":"Synthetic integration test only, not true negative sampling",
            "frame_provenance":"Synthetic record population, no real nonfire labels",
            "source_url":"https://example.org/frame",
            "rights_url":"https://example.org/rights",
            "units":[{"sampling_unit_id":"frame-1","region_id":"region-1",
                       "latitude":37.0,"longitude":-120.0,
                       "decision_at":"2018-07-01T00:00:00Z"}]}
        file=self.root/"frame.json"
        file.write_text(json.dumps(frame),encoding="utf-8")
        self.queue=prepare_queue(self.db,at=OLD,years=[2017,2018],
                                  frame_path=file,max_controls=1)
        self.queue_path.write_text(json.dumps(self.queue),encoding="utf-8")
        self.original_batches=[dict(b) for b in self.queue["source_batches"]]

    def verify(self,**opts):
        return verify_leads(self.queue_path,self.db,
            max_leads=4,fetch_page=self.provider.page,
            fetch_metadata=metadata,clock=lambda:NEW,**opts)

    def test_reconcile_original_real_archive_exact_ids_and_bytes(self):
        result,blobs=self.verify()
        self.assertEqual(result["reviewed_official_leads"],4)
        self.assertEqual(result["official_source_requests"],2)
        self.assertEqual(result["source_revisions"],0)
        self.assertEqual(result["transport"],"injected_test_transport")
        self.assertFalse(result["model_ready"])
        self.assertEqual(result["independently_verified_negative_labels"],0)
        self.assertEqual(len(blobs),2)
        self.assertEqual(result["original_queue_sha256"],
                         hashlib.sha256(self.queue_path.read_bytes()).hexdigest())
        self.assertTrue(all(x["source_record_status"]=="same_content_as_archived"
                            for x in result["findings"]))
        self.assertEqual(len(self.provider.requests),2)
        self.assertEqual(set(self.provider.requests[0]["objectIds"].split(",")),
                         {"11","12"})
        for raw, evidence in zip(
                [blobs[name] for name in sorted(blobs)], result["source_response_evidence"]):
            self.assertEqual(evidence["sha256"],hashlib.sha256(raw).hexdigest())
            self.assertEqual(evidence["bytes"],len(raw))

    def test_detect_source_revision_not_fire_spread(self):
        self.provider.revised=True
        result,_=self.verify()
        self.assertEqual(result["source_revisions"],1)
        updated=[x for x in result["findings"]
                 if x["source_record_status"]=="source_revision_since_archival"]
        self.assertEqual(len(updated),1)
        self.assertEqual(updated[0]["case_id"],"official:2017:11")
        self.assertEqual(result["independent_outcomes_verified"],0)

    def test_source_disappearance_refuses_to_infer_no_fire(self):
        self.provider.omit=True
        with self.assertRaisesRegex(ValueError,"missing requested polygon"):
            self.verify()

    def test_source_identity_revision_fails_closed(self):
        self.provider.wrong_identity=True
        with self.assertRaisesRegex(ValueError,"GlobalID changed"):
            self.verify()

    def test_tampered_review_queue_identity_fails_before_network(self):
        self.queue["cases"][0]["source_name"]="Altered agency name"
        self.queue_path.write_text(json.dumps(self.queue),encoding="utf-8")
        with self.assertRaisesRegex(ValueError,"name was altered"):
            self.verify()
        self.assertEqual(len(self.provider.requests),0)

    def test_queue_year_batch_mismatch_and_time_reversal(self):
        self.queue["source_batches"].pop()
        self.queue_path.write_text(json.dumps(self.queue))
        with self.assertRaisesRegex(ValueError,"batch years are inconsistent"):
            self.verify()
        # Restore the queue before testing the independent chronology guard.
        self.queue["source_batches"] = self.original_batches
        self.queue_path.write_text(json.dumps(self.queue))
        with self.assertRaisesRegex(ValueError,"cannot predate"):
            verify_leads(self.queue_path,self.db,max_leads=4,
                         fetch_page=self.provider.page,fetch_metadata=metadata,
                         clock=lambda:"2016-01-01T00:00:00Z")

    def test_budget_and_untrusted_metadata_gate(self):
        with self.assertRaisesRegex(ValueError,"max_leads"):
            verify_leads(self.queue_path,self.db,max_leads=3,
                         fetch_page=self.provider.page,fetch_metadata=metadata)
        def forged_metadata():
            m=metadata();m["serviceItemId"]="forged-provider"
            return m
        with self.assertRaisesRegex(ValueError,"contract drift"):
            verify_leads(self.queue_path,self.db,max_leads=4,
                         fetch_page=self.provider.page,
                         fetch_metadata=forged_metadata)
        self.assertFalse(self.provider.requests)

    def test_immutable_byte_export_verifiable_without_overwrite(self):
        report,blobs=self.verify()
        path=self.root/"live-refresh.json"
        source_dir=self.root/"provider-bytes"
        write_evidence(path,source_dir,report,blobs,
                       input_files=(self.queue_path,self.db))
        self.assertEqual(json.loads(path.read_text())["reviewed_official_leads"],4)
        for name,raw in blobs.items():
            self.assertEqual((source_dir/name).read_bytes(),raw)
        with self.assertRaisesRegex(ValueError,"new and disjoint"):
            write_evidence(path,source_dir,report,blobs,
                           input_files=(self.queue_path,self.db))
        self.assertTrue(self.db.is_file())
        self.assertTrue(self.queue_path.is_file())
        with self.assertRaisesRegex(ValueError,"new and disjoint"):
            write_evidence(self.db,self.root/"new-provider-bytes",report,blobs,
                           input_files=(self.queue_path,self.db))


if __name__=="__main__":
    unittest.main()
