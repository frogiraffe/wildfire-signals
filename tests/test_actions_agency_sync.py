"""End-to-end deterministic synthetic Actions artifact sync regression tests."""
from __future__ import annotations

from datetime import datetime
from email.message import Message
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request
import zipfile

from fire_public.actions_agency_sync import (
    GitHubArtifacts, _artifact_host, _extract_agency, _trusted_run, sync)
from fire_public.agency_vault import verify
from fire_public.analysis_receipt import build_receipt, write_receipt
from fire_public.prospective_replay import open_archive, replay
from fire_public.agency_vault import research_workspace, rebuild_sqlite

REPO="frogiraffe/wildfire-signals"
HEAD="a"*40


def sample(run_id=500, hour=0, *, agency="complete", expected_sha=HEAD, captured_hour=None):
    scan=f"2026-10-12T{hour:02d}:17:00Z"
    capture=f"2026-10-12T{(hour if captured_hour is None else captured_hour):02d}:18:00Z"
    row={"kind":"agency_incident","provider":"cwfis","official_id":"CA-1",
         "name":"Bounded collection example",
         "incident_kind":"active_wildland_fire","latitude":45.0,
         "longitude":-101.0,"modified_at":scan,"last_seen_at":scan,
         "agency_status":"OC"}
    snap={"manifest":{"schema_version":1,"truncated":False,
         "data_status":"fresh" if agency=="complete" else "partial",
         "last_scan_at":scan,"source_errors":[] if agency=="complete" else ["cwfis"]},
         "sources":[{"key":"cwfis","status":agency},
                    {"key":"nifc_wfigs","status":"complete"}],
         "incidents":[row],"events":[],"matches":[]}
    raw,_=build_receipt(snap,captured_at=capture,run_id=str(run_id),
                        head_sha=expected_sha,snapshot_key="snapshot:"+"b"*64)
    with tempfile.TemporaryDirectory() as root:
        name=write_receipt(Path(root),raw,scan_at=scan).name
    return name,raw


def zipped(name,raw,extra=None):
    buf=BytesIO()
    with zipfile.ZipFile(buf,"w",compression=zipfile.ZIP_STORED) as z:
        if name is not None:
            z.writestr(name,raw)
        z.writestr("firms-pixel-scan-20261012.json.gz",b"pixel stream is not ingested")
        if extra:
            for key,value in extra.items():
                z.writestr(key,value)
    return buf.getvalue()


def metadata(run_id,artifact_id,at="2026-10-12T00:18:30Z",*, expired=False,attempt=1):
    return {"id":artifact_id,"name":f"analysis-receipt-{run_id}-{attempt}",
            "workflow_run":{"id":run_id},"expired":expired,"size_in_bytes":1555,
            "created_at":at,"expires_at":"2027-01-10T00:18:30Z"}


def run(run_id=500,hour=0,*,head=HEAD):
    return {"id":run_id,"path":".github/workflows/collect.yml",
            "name":"Collect public fire observations",
            "head_branch":"main","repository":{"full_name":REPO},
            "status":"completed","conclusion":"success","run_attempt":1,
            "head_sha":head,"run_started_at":f"2026-10-12T{hour:02d}:17:00Z"}


class FakeClient:
    def __init__(self, pages, runs, zip_by_id):
        self.pages=pages
        self.runs=runs
        self.zip_by_id=zip_by_id
        self.calls=[]
    def list_artifacts(self,page):
        self.calls.append(("list",page))
        return {"total_count":sum(len(p) for p in self.pages),
                "artifacts":self.pages[page-1] if page<=len(self.pages) else []}
    def get_run(self,run_id):
        self.calls.append(("run",run_id))
        return self.runs[run_id]
    def download_zip(self,aid):
        self.calls.append(("download",aid))
        return self.zip_by_id[aid]


class ActionsAgencySyncTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.vault=self.root/"private"

    def client(self):
        first,z1=sample(500,0)
        second,z2=sample(501,6,agency="failed")
        return FakeClient([[metadata(501,2,"2026-10-12T06:18:30Z"),
                            metadata(500,1)]],
                          {500:run(500,0),501:run(501,6)},
                          {1:zipped(first,z1),2:zipped(second,z2)})

    def test_real_pipeline_download_original_then_replay_historical_at_time(self):
        client=self.client()
        result=sync(self.vault,client)
        self.assertEqual(result["new_original_agency_receipts"],2)
        self.assertEqual(result["downloaded_archives"],2)
        self.assertEqual(result["existing_original_agency_receipts"],0)
        self.assertFalse(result["discovery_exhaustive"] is False)
        self.assertEqual(result["vault_receipts"],2)
        self.assertEqual(verify(self.vault)["source_health"]["source_failure_counts"]["cwfis"],1)
        again=sync(self.vault,client)
        self.assertEqual(again["new_original_agency_receipts"],0)
        self.assertEqual(again["already_checked_archives"],2)
        self.assertEqual(again["downloaded_archives"],0)
        self.assertEqual(again["vault_receipts"],2)
        db=self.root/"asof.sqlite3"
        rebuilt=rebuild_sqlite(self.vault,db)
        self.assertEqual(rebuilt["historical_scans"],2)
        store=open_archive(db)
        try:
            historical=replay(store,at="2026-10-12T03:00:00Z",provider="cwfis")
            self.assertEqual(historical["cases"][0]["latest_availability"],"listed")
            latest=replay(store,at="2026-10-12T08:00:00Z",provider="cwfis")
            self.assertEqual(latest["cases"][0]["latest_availability"],"source_unavailable")
            self.assertIsNone(latest["cases"][0]["latest_agency_status"])
        finally:store.close()
        view=research_workspace(self.vault,self.root/"research",
                                provider="cwfis",at="2026-10-12T08:00:00Z")
        self.assertEqual(view["cases"],1)
        self.assertTrue((self.root/"research"/"index.html").is_file())

    def test_dry_run_never_downloads_or_creates_private_vault(self):
        client=self.client()
        result=sync(self.vault,client,dry_run=True)
        self.assertEqual(result["selected_archives"],2)
        self.assertEqual(result["downloaded_archives"],0)
        self.assertEqual(client.calls,[("list",1)])
        self.assertFalse(self.vault.exists())
        self.assertTrue(result["dry_run"])

    def test_pixel_only_artifacts_not_misrepresented_as_agency(self):
        c=self.client()
        c.zip_by_id[1]=zipped(None,None)
        result=sync(self.vault,c)
        self.assertEqual(result["pixel_only_or_no_agency_receipt"],1)
        self.assertEqual(result["vault_receipts"],1)
        self.assertEqual(result["new_original_agency_receipts"],1)

    def test_all_pixel_only_no_private_vault_created(self):
        c=self.client()
        c.zip_by_id={1:zipped(None,None),2:zipped(None,None)}
        result=sync(self.vault,c)
        self.assertEqual(result["new_original_agency_receipts"],0)
        self.assertEqual(result["vault_receipts"],0)
        self.assertTrue((self.vault/"receipts").is_dir())
        self.assertTrue((self.vault/".actions-sync-state.json").is_file())

    def test_expired_and_page_limit_have_explicit_incomplete_status(self):
        client=self.client()
        a=client.pages[0][0]
        a["expired"]=True
        result=sync(self.vault,client,dry_run=True,max_downloads=1)
        self.assertEqual(result["expired_candidates"],1)
        self.assertEqual(result["selected_archives"],1)
        self.assertEqual(result["discovery_exhaustive"],True)
        client=self.client()
        result=sync(self.vault,client,dry_run=True,max_downloads=1)
        self.assertEqual(result["outside_download_limit"],1)
        self.assertFalse(result["discovery_exhaustive"])
        full=[{"id":i+10,"name":"unrelated-"+str(i)} for i in range(100)]
        other=FakeClient([full],[ ],{})
        result=sync(self.vault,other,dry_run=True,pages=1)
        self.assertTrue(result["listing_page_cap_reached"])
        self.assertFalse(result["discovery_exhaustive"])

    def test_since_cutoff_skips_older_artifact_without_claiming_full_recovery(self):
        c=self.client()
        result=sync(self.vault,c,dry_run=True,since="2026-10-12T05:00:00Z")
        self.assertEqual(result["selected_archives"],1)
        self.assertFalse(result["discovery_exhaustive"])
        with self.assertRaises(ValueError):sync(self.vault,c,since="yesterday")
        with self.assertRaises(ValueError):sync(self.vault,c,pages=0)
        with self.assertRaises(ValueError):sync(self.vault,c,max_downloads=201)

    def test_bounded_catchup_advances_to_older_unprocessed_artifacts(self):
        client=self.client()
        first=sync(self.vault,client,max_downloads=1)
        self.assertEqual(first["downloaded_archives"],1)
        self.assertEqual(first["outside_download_limit"],1)
        self.assertFalse(first["discovery_exhaustive"])
        second=sync(self.vault,client,max_downloads=1)
        self.assertEqual(second["downloaded_archives"],1)
        self.assertEqual(second["already_checked_archives"],1)
        self.assertEqual(second["new_original_agency_receipts"],1)
        self.assertTrue(second["discovery_exhaustive"])
        third=sync(self.vault,client,max_downloads=1)
        self.assertEqual(third["downloaded_archives"],0)
        self.assertEqual(third["already_checked_archives"],2)
        self.assertEqual(third["vault_receipts"],2)
        self.assertEqual(verify(self.vault)["manifest"]["file_count"],2)

    def test_progress_recovers_missing_source_without_trusting_cached_agency_bytes(self):
        client=self.client()
        sync(self.vault,client)
        original=next((self.vault/"receipts").glob("agency-*"))
        original.unlink()
        again=sync(self.vault,client)
        self.assertEqual(again["new_original_agency_receipts"],1)
        self.assertEqual(again["already_checked_archives"],1)
        self.assertEqual(again["vault_receipts"],2)

    def test_progress_is_never_ground_truth_and_bad_file_rejected(self):
        client=self.client()
        sync(self.vault,client,max_downloads=1)
        progress=self.vault/".actions-sync-state.json"
        content=json.loads(progress.read_text())
        self.assertEqual(content["schema_version"],1)
        self.assertEqual(progress.stat().st_mode & 0o777,0o600)
        content["checked"]["2"]["receipt_sha256"]="0"*64
        progress.write_text(json.dumps(content))
        with self.assertRaisesRegex(ValueError,"archived original changed"):
            sync(self.vault,client)
        progress.write_text("{not-json")
        with self.assertRaises(ValueError):
            sync(self.vault,client)

    def test_pixel_only_progress_skips_known_no_agency_artifact(self):
        client=self.client()
        client.zip_by_id[2]=zipped(None,None)
        first=sync(self.vault,client,max_downloads=1)
        self.assertEqual(first["pixel_only_or_no_agency_receipt"],1)
        second=sync(self.vault,client,max_downloads=1)
        self.assertEqual(second["new_original_agency_receipts"],1)
        self.assertEqual(second["already_checked_archives"],1)
        self.assertEqual(second["outside_download_limit"],0)
        third=sync(self.vault,client,max_downloads=1)
        self.assertEqual(third["downloaded_archives"],0)
        self.assertEqual(third["already_checked_archives"],2)

    def test_reject_foreign_workflow_and_failed_run_before_downloading(self):
        for change in [{"path":".github/workflows/test.yml"},
                       {"conclusion":"failure"},{"status":"in_progress"},
                       {"head_branch":"feature"},
                       {"head_sha":"broken"},
                       {"repository":{"full_name":"attacker/forged"}}]:
            client=self.client()
            client.runs[500].update(change)
            with self.subTest(change=change):
                with self.assertRaisesRegex(ValueError,"not from a successful"):
                    sync(self.vault,client)
                self.assertNotIn(("download",1),client.calls)

    def test_reject_receipt_run_and_commit_mismatch_before_ingest(self):
        c=self.client()
        name,raw=sample(999,0)
        c.zip_by_id[1]=zipped(name,raw)
        # Newest artifact already ingested, then mismatch fails. Existing evidence remains safe.
        with self.assertRaisesRegex(ValueError,"does not belong"):
            sync(self.vault,c)
        self.assertEqual(verify(self.vault)["manifest"]["file_count"],1)

    def test_reject_outside_time_claim_and_changed_zip_content(self):
        c=self.client()
        name,raw=sample(500,0,captured_hour=3)
        c.zip_by_id[1]=zipped(name,raw)
        with self.assertRaisesRegex(ValueError,"inconsistent"):
            sync(self.vault,c)
        c=self.client()
        name,raw=sample(500,0)
        c.zip_by_id[1]=zipped(name,raw+b"malicious")
        with self.assertRaisesRegex(ValueError,"checksum"):
            sync(self.vault,c)

    def test_zip_slip_and_duplicate_agency_members_fail_closed(self):
        name,raw=sample(500,0)
        c=self.client()
        c.zip_by_id[1]=zipped(name,raw,{"../attack.txt":b"escape"})
        with self.assertRaisesRegex(ValueError,"unsafe"):
            sync(self.vault,c)
        c=self.client()
        other,z=sample(500,6)
        c.zip_by_id[1]=zipped(name,raw,{other:z})
        with self.assertRaisesRegex(ValueError,"more than one"):
            sync(self.vault,c)

    def test_bad_artifact_metadata_and_expiry_state_fail(self):
        client=self.client()
        client.pages[0][0]["workflow_run"]={"id":999}
        with self.assertRaisesRegex(ValueError,"conflict"):
            sync(self.vault,client,dry_run=True)
        client=self.client()
        del client.pages[0][0]["expired"]
        with self.assertRaisesRegex(ValueError,"expiry"):
            sync(self.vault,client,dry_run=True)

    def test_never_send_bearer_credentials_to_signed_blob_redirect(self):
        class _Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*_):pass
            def read(self,n):return b"SAFE ZIP BYTES"
        class _Opener:
            def __init__(self):self.seen=[]
            def open(self,req,timeout):
                self.seen.append(req)
                if len(self.seen)==1:
                    headers=Message()
                    headers["Location"]="https://productionresultssa1.blob.core.windows.net/c/receipt.zip?sig=test"
                    raise HTTPError(req.full_url,302,"Found",headers,None)
                return _Response()
        api=GitHubArtifacts("private-token-never-logged")
        fake=_Opener()
        api._opener=fake
        self.assertEqual(api.download_zip(123),b"SAFE ZIP BYTES")
        self.assertIn("Bearer private-token",fake.seen[0].get_header("Authorization"))
        self.assertIsNone(fake.seen[1].get_header("Authorization"))
        self.assertTrue(_artifact_host(fake.seen[1].full_url))
        self.assertFalse(_artifact_host("https://blob.core.windows.net.evil.tld/evil"))
        self.assertFalse(_artifact_host("http://productionresultssa1.blob.core.windows.net/"))
        self.assertFalse(_artifact_host("https://evil.com/"))
        bad=_Opener()
        def malicious(req,timeout):
            headers=Message();headers["Location"]="https://evil.com/tokens"
            raise HTTPError(req.full_url,302,"Found",headers,None)
        bad.open=malicious
        api._opener=bad
        with self.assertRaisesRegex(ValueError,"untrusted"):
            api.download_zip(123)


if __name__=="__main__":
    unittest.main()
