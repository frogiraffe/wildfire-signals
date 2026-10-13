"""Independent original agency source review bridge regression tests.

Genuine-format, synthetic originals enter PixelArchive and HistoryStore through
the production importers. These fixtures are NOT real wildfire labels.
"""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest

from fire_public.analysis_receipt import build_receipt,write_receipt
from fire_public.history import HistoryStore
from fire_public.receipt_history import import_receipts
from fire_public.collect import FIRMS_SOURCES
from fire_public.pixel_history import import_release_assets
from fire_public.observational_cohort import build_observational_cohort,export_cohort
from fire_public.agency_cohort_review import (
    build_agency_review_candidates, export_review,read_unlabeled_cohort)
from test_pixel_history import make_release,pixel

BASE=datetime(2026,10,12,0,0,tzinfo=timezone.utc)
REGIONS=[
    {"region_id":"CASE_A","latitude":0,"longitude":179.9,"radius_km":85},
    {"region_id":"CASE_B","latitude":1,"longitude":10,"radius_km":85},
]
HEAD="a"*40


class AgencyCohortReviewTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.pixels=self.root/"source-pixels.sqlite3"
        self.releases=self.root/"research-assets"
        self.agency_db=self.root/"agency-history.sqlite3"
        self.receipts=self.root/"agency-originals"
        self.cohort=self.root/"private-observational-cohort"

    def fir_blob(self):
        for i in range(14):
            when=BASE+timedelta(hours=2*i+1)
            observation=pixel(FIRMS_SOURCES[0],
                when=BASE+timedelta(hours=2*i,minutes=30),
                latitude=0,longitude=179.91,ident=f"signal-{i}")
            make_release(self.releases/f"scan-{i}",when,[observation])
        imported=import_release_assets(self.pixels,self.releases)
        self.assertEqual(imported["imported_scans"],14)
        cohort=build_observational_cohort(self.pixels,REGIONS,
            start_at=(BASE+timedelta(hours=24)).isoformat(),
            end_at=(BASE+timedelta(hours=25)).isoformat(),
            cadence_hours=1,lookback_hours=24,target_hours=24)
        export_cohort(cohort,self.cohort)
        self.assertEqual(len(cohort["rows"]),2)
        return cohort

    def agency_scan(self,hour,*,records=(),failed=(),run=None):
        scan=BASE+timedelta(hours=hour,minutes=17)
        captured=BASE+timedelta(hours=hour,minutes=18)
        def row(provider,oid,lat,lon,status="OC",name=None):
            return {
                "kind":"agency_incident","provider":provider,
                "official_id":oid,"name":name or oid,
                "incident_kind":"active_wildland_fire",
                "latitude":lat,"longitude":lon,
                "modified_at":scan.isoformat(),"agency_status":status,
                "last_seen_at":scan.isoformat()
            }
        source_rows=[{"key":p,"status":"failed" if p in failed else "complete"}
                     for p in ("nifc_wfigs","cwfis")]
        data={"manifest":{"schema_version":1,
              "last_scan_at":scan.isoformat(),"truncated":False,
              "data_status":"partial" if failed else "fresh",
              "source_errors":list(failed)},
              "sources":source_rows,
              "incidents":[row(*x) for x in records],
              "events":[],"matches":[]}
        payload,_=build_receipt(data,captured_at=captured.isoformat(),
                                 run_id=str(run or (100+hour)),
                                 head_sha=HEAD,snapshot_key="snapshot:"+"b"*64)
        write_receipt(self.receipts,payload,scan_at=scan.isoformat())

    def agency_import(self):
        store=HistoryStore(self.agency_db)
        try:return import_receipts(store,self.receipts)
        finally:store.close()

    def test_real_importer_to_cohort_review_leads_without_any_labels(self):
        cohort=self.fir_blob()
        self.agency_scan(20,records=[
            ("cwfis","PREEXISTING",0,-179.92,"OC"),
            ("nifc_wfigs","REMOTE",25,25,"OC")])
        self.agency_scan(26,records=[
            ("cwfis","PREEXISTING",0,-179.92,"OC"),
            ("cwfis","NEW_SOURCE_ID",0,179.93,"UC")])
        self.agency_scan(30,failed=("cwfis",),records=[
            ("cwfis","SHOULD_IGNORE_FAILED",0,179.9,"OC")])
        self.agency_scan(34,records=[
            ("cwfis","NEW_SOURCE_ID",0,179.93,"UC"),
            ("nifc_wfigs","OTHER_PROVIDER",0,179.93,"OC")])
        self.assertEqual(self.agency_import()["imported_scans"],4)
        result=build_agency_review_candidates(self.cohort,self.agency_db)
        self.assertEqual(result["verified_independent_fire_labels"],0)
        self.assertEqual(result["verified_negative_fire_labels"],0)
        self.assertIsNone(result["fire_probability"])
        self.assertFalse(result["model_training_allowed"])
        leads=result["review_leads"]
        self.assertEqual([(r["agency_provider"],r["official_id"]) for r in leads],
                         [("cwfis","NEW_SOURCE_ID"),("cwfis","PREEXISTING"),
                          ("nifc_wfigs","OTHER_PROVIDER")])
        past=next(x for x in leads if x["official_id"]=="PREEXISTING")
        self.assertTrue(past["prior_listed_in_available_history"])
        self.assertEqual(past["lead_status"],"preexisting_agency_source_listing")
        new=next(x for x in leads if x["official_id"]=="NEW_SOURCE_ID")
        self.assertFalse(new["prior_listed_in_available_history"])
        self.assertFalse(new["ignition_time_established"])
        self.assertEqual(new["lead_status"],
           "first_in_available_receipt_history_not_proven_ignition")
        self.assertEqual(new["first_post_decision_listed_at"],
                         (BASE+timedelta(hours=26,minutes=18)).isoformat())
        self.assertNotEqual(new["review_lead_id"],
                             next(x for x in leads if x["official_id"]=="OTHER_PROVIDER")["review_lead_id"])
        self.assertEqual(new["review_status"],"unresolved")
        self.assertFalse(new["event_identity_verified"])
        self.assertFalse(new["satellite_association_verified"])
        self.assertIsNone(new["independent_outcome_label"])
        self.assertIsNone(new["negative_fire_label"])
        self.assertEqual(len(new["receipt_sha256"]),64)
        self.assertEqual(len(new["original_observation_sha256"]),64)
        self.assertNotIn("REMOTE",str(result))
        self.assertNotIn("SHOULD_IGNORE_FAILED",str(result))
        self.assertEqual(len(result["source_coverage_audit"]),2)
        second=next(x for x in result["source_coverage_audit"]
                    if x["sample_id"]==cohort["rows"][1]["sample_id"])
        self.assertEqual(second["candidate_source_listings"],0)
        self.assertIsNone(second["target_label"])
        self.assertFalse(second["absence_implies_no_wildfire"])
        first=result["source_coverage_audit"][0]
        self.assertTrue(first["right_censored_by_evidence_cutoff"])
        self.assertEqual(first["providers"]["cwfis"]["post_decision_failed_receipts"],1)
        self.assertEqual(first["providers"]["cwfis"]["post_decision_complete_receipts"],2)
        self.assertEqual(result["counts"]["samples_with_review_leads"],1)
        self.assertEqual(result["counts"]["candidate_agency_source_listings"],3)
        self.assertEqual(result["counts"]["verified_negative_labels"],0)

        private=self.root/"agency-review"
        files=export_review(result,private)
        self.assertEqual(files["review_leads"],3)
        self.assertEqual(files["samples"],2)
        self.assertEqual(files["independent_fire_labels"],0)
        self.assertEqual(private.stat().st_mode & 0o777,0o700)
        for item in private.iterdir():
            self.assertEqual(item.stat().st_mode & 0o777,0o600)
        manifest=json.loads((private/"manifest.json").read_text())
        for name,meta in manifest["files"].items():
            self.assertEqual(hashlib.sha256((private/name).read_bytes()).hexdigest(),
                             meta["sha256"])
        html=(private/"review.html").read_text()
        self.assertIn("unlabeled",html)
        self.assertNotIn("<script",html)
        self.assertNotIn("http",html)
        with self.assertRaisesRegex(ValueError,"new private"):
            export_review(result,private)

    def test_source_outage_and_absence_after_complete_scan_are_unknown_not_negative(self):
        self.fir_blob()
        self.agency_scan(20,records=[("cwfis","OLD",0,179.92,"OC")])
        self.agency_scan(26,failed=("cwfis",),records=[
            ("cwfis","OLD",0,179.92,"OC")])
        self.agency_scan(30,records=[])
        self.agency_import()
        report=build_agency_review_candidates(self.cohort,self.agency_db)
        self.assertEqual(report["review_leads"],[])
        self.assertEqual(report["counts"]["candidate_agency_source_listings"],0)
        self.assertEqual(report["counts"]["verified_negative_labels"],0)
        self.assertEqual(report["source_coverage_audit"][0]["providers"]["cwfis"]
                         ["post_decision_complete_receipts"],1)
        self.assertTrue(report["source_coverage_audit"][0]["right_censored_by_evidence_cutoff"])

    def test_future_receipts_cannot_become_predecision_features(self):
        self.fir_blob()
        self.agency_scan(20,records=[])
        self.agency_scan(26,records=[("cwfis","LATER",0,179.92,"OC")])
        self.agency_scan(46,records=[("cwfis","LATEST",0,179.92,"UC")])
        self.agency_import()
        full=build_agency_review_candidates(self.cohort,self.agency_db)
        early=build_agency_review_candidates(
            self.cohort,self.agency_db,through=(BASE+timedelta(hours=25)).isoformat())
        self.assertEqual(early["review_leads"],[])
        self.assertEqual(len(full["review_leads"]),2)
        self.assertTrue(early["source_coverage_audit"][0]
                        ["right_censored_by_evidence_cutoff"])
        self.assertEqual(full["source_coverage_audit"][0]["decision_at"],
                         (BASE+timedelta(hours=24)).isoformat())
        self.assertTrue(all(r["independent_outcome_label"] is None for r in full["review_leads"]))

    def test_tampered_cohort_manifest_or_training_label_rejected(self):
        self.fir_blob()
        self.agency_scan(26,records=[("cwfis","X",0,179.92)])
        self.agency_import()
        first=(self.cohort/"observations.jsonl")
        original=first.read_bytes()
        first.write_bytes(original+b"forged")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            build_agency_review_candidates(self.cohort,self.agency_db)
        first.write_bytes(original)
        self.assertEqual(read_unlabeled_cohort(self.cohort)[2],
            hashlib.sha256((self.cohort/"manifest.json").read_bytes()).hexdigest())
        rows=[json.loads(x) for x in original.splitlines()]
        rows[0]["target_label"]=0
        first.write_bytes(b"".join((json.dumps(x,sort_keys=True,separators=(',',':'))+"\n").encode() for x in rows))
        meta=json.loads((self.cohort/"manifest.json").read_text())
        meta["files"]["observations.jsonl"]["sha256"]=hashlib.sha256(first.read_bytes()).hexdigest()
        (self.cohort/"manifest.json").write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError,"UNLABELED"):
            build_agency_review_candidates(self.cohort,self.agency_db)

    def test_cli_offline_source_bridge_and_no_overwrite(self):
        self.fir_blob()
        self.agency_scan(26,records=[("cwfis","X",0,179.92)])
        self.agency_import()
        destination=self.root/"output"
        command=[sys.executable,"-m","fire_public.agency_cohort_review",
                 "--cohort-dir",str(self.cohort),"--agency-db",str(self.agency_db),
                 "--output-dir",str(destination)]
        proc=subprocess.run(command,capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["review_leads"],1)
        self.assertTrue((destination/"agency-review-leads.jsonl").is_file())
        self.assertNotEqual(subprocess.run(command,capture_output=True).returncode,0)


if __name__=="__main__":
    unittest.main()
