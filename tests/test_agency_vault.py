"""Durable original agency evidence vault: synthetic receipts, recoverability and safety."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile

from fire_public.analysis_receipt import build_receipt, write_receipt
from fire_public.agency_vault import (
    ingest, verify, export_bundle, restore_bundle, rebuild_sqlite)
from fire_public.prospective_replay import open_archive, replay
from fire_public.receipt_history import incident_at
from fire_public.history import HistoryStore


class AgencyVaultTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.source=self.root/"downloaded-from-Actions"
        self.source.mkdir()
        self.vault=self.root/"permanent-private-originals"

    def receipt(self,hour:int,*,status="complete",listed=True,stage="OC",
                directory=None,run=None):
        scan=f"2026-10-12T{hour:02d}:17:00Z"
        captured=f"2026-10-12T{hour:02d}:18:00Z"
        row={"kind":"agency_incident","provider":"cwfis","official_id":"CA-A",
             "name":"Example A","incident_kind":"active_wildland_fire",
             "latitude":55.0,"longitude":-110.0,"modified_at":scan,
             "agency_status":stage,"last_seen_at":scan}
        snapshot={
          "manifest":{"schema_version":1,"last_scan_at":scan,
                      "truncated":False,"data_status":"fresh" if status=="complete" else "partial",
                      "source_errors":[] if status=="complete" else ["cwfis"]},
          "sources":[{"key":"nifc_wfigs","status":"complete"},
                     {"key":"cwfis","status":status}],
          "incidents":[row] if listed else [],
          "events":[],"matches":[]
        }
        raw,_=build_receipt(snapshot,captured_at=captured,run_id=str(run or 100+hour),
                  head_sha="a"*40,snapshot_key="snapshot:"+"b"*64)
        return write_receipt(directory or self.source,raw,scan_at=scan)

    def fill(self):
        self.receipt(0)
        self.receipt(6,status="failed",listed=True)
        self.receipt(12,listed=False)
        self.receipt(18,stage="UC")

    def test_full_pipeline_ingest_restore_rebuild_and_decision_time(self):
        self.fill()
        expected={path.name:path.read_bytes() for path in self.source.iterdir()}
        first=ingest(self.vault,self.source)
        self.assertEqual(first["new_original_receipts"],4)
        self.assertEqual(first["vault_receipt_count"],4)
        self.assertEqual(ingest(self.vault,self.source)["new_original_receipts"],0)
        state=verify(self.vault)
        self.assertEqual(state["manifest"]["file_count"],4)
        self.assertEqual(state["source_health"]["receipt_count"],4)
        self.assertEqual(state["source_health"]["source_failure_counts"]["cwfis"],1)
        self.assertEqual(state["manifest"]["negative_fire_labels_created"],0)
        self.assertRegex(state["manifest_sha256"],r"^[a-f0-9]{64}$")
        bundle=self.root/"durable-private-backup.zip"
        exported=export_bundle(self.vault,bundle)
        self.assertEqual(exported["manifest_sha256"],state["manifest_sha256"])
        self.assertEqual(exported["receipts"],4)
        self.assertEqual(bundle.stat().st_mode & 0o777,0o600)
        with zipfile.ZipFile(bundle) as archive:
            self.assertEqual(set(archive.namelist()),
                 {"manifest.json",*{"receipts/"+key for key in expected}})
            self.assertEqual({name:archive.read("receipts/"+name)
                              for name in expected},expected)
        # Original downloaded files may expire; restoring a backup must suffice.
        shutil.rmtree(self.source)
        restored=self.root/"disaster-recovered-originals"
        self.assertEqual(restore_bundle(bundle,restored)["restored_receipts"],4)
        self.assertEqual(restored.stat().st_mode & 0o777,0o700)
        self.assertEqual(verify(restored)["manifest_sha256"],state["manifest_sha256"])
        for name,raw in expected.items():
            path=restored/"receipts"/name
            self.assertEqual(path.read_bytes(),raw)
            self.assertEqual(path.stat().st_mode & 0o777,0o600)
        database=self.root/"rebuilt-evidence.sqlite3"
        rebuilt=rebuild_sqlite(restored,database)
        self.assertEqual(rebuilt["historical_scans"],4)
        self.assertEqual(rebuilt["sqlite_integrity"],"ok")
        self.assertEqual(database.stat().st_mode & 0o777,0o600)
        conn=open_archive(database)
        try:
            report=replay(conn,at="2026-10-12T23:00:00Z",provider="cwfis")
            self.assertEqual(report["known_source_identities"],1)
            self.assertEqual([t["availability"] for t in report["cases"][0]["timeline"]],
                 ["listed","source_unavailable","not_listed_in_complete_scan","listed"])
            self.assertEqual(report["cases"][0]["latest_agency_status"],"UC")
            self.assertEqual(report["verified_extinguishment_labels"],0)
            earlier=replay(conn,at="2026-10-12T01:00:00Z",provider="cwfis")
            self.assertEqual(len(earlier["cases"][0]["timeline"]),1)
            self.assertEqual(earlier["cases"][0]["timeline"][0]["agency_status"],"OC")
        finally:
            conn.close()
        with self.assertRaisesRegex(ValueError,"new private output"):
            rebuild_sqlite(restored,database)
        with self.assertRaisesRegex(ValueError,"new private file"):
            export_bundle(restored,bundle)
        with self.assertRaisesRegex(ValueError,"new, private output"):
            restore_bundle(bundle,restored)

    def test_incremental_old_and_new_receipts_and_conflict_are_distinct(self):
        original=self.receipt(0)
        self.assertEqual(ingest(self.vault,self.source)["new_original_receipts"],1)
        later=self.receipt(6)
        self.assertEqual(ingest(self.vault,self.source)["new_original_receipts"],1)
        self.assertEqual(verify(self.vault)["manifest"]["file_count"],2)
        incoming=self.root/"alternate-download"
        incoming.mkdir()
        self.receipt(0,directory=incoming,run=999)
        before=verify(self.vault)["manifest_sha256"]
        with self.assertRaisesRegex(ValueError,"conflicting agency scan UTC"):
            ingest(self.vault,incoming)
        self.assertEqual(verify(self.vault)["manifest_sha256"],before)
        self.assertEqual(original.read_bytes(),
                         (self.vault/"receipts"/original.name).read_bytes())
        self.assertEqual(later.read_bytes(),
                         (self.vault/"receipts"/later.name).read_bytes())

    def test_corrupt_original_cannot_be_imported_and_corrupt_vault_blocks_restore(self):
        file=self.receipt(0)
        raw=file.read_bytes()
        file.write_bytes(raw+b"tampered")
        with self.assertRaisesRegex(ValueError,"checksum"):
            ingest(self.vault,self.source)
        file.write_bytes(raw)
        ingest(self.vault,self.source)
        archived=self.vault/"receipts"/file.name
        archived.write_bytes(raw+b"tamper")
        with self.assertRaisesRegex(ValueError,"checksum"):
            verify(self.vault)
        with self.assertRaisesRegex(ValueError,"checksum"):
            export_bundle(self.vault,self.root/"should-not-export.zip")
        with self.assertRaisesRegex(ValueError,"checksum"):
            rebuild_sqlite(self.vault,self.root/"never-create.sqlite3")
        self.assertFalse((self.root/"never-create.sqlite3").exists())

    def test_zip_slip_extra_member_and_manifest_tamper_fail_without_restoration(self):
        self.receipt(0)
        ingest(self.vault,self.source)
        bundle=self.root/"good.zip"
        export_bundle(self.vault,bundle)
        bad=self.root/"extra.zip"
        with zipfile.ZipFile(bundle) as original,zipfile.ZipFile(bad,"w") as copy:
            for entry in original.infolist():
                copy.writestr(entry,original.read(entry.filename))
            copy.writestr("../outside-secret","unsafe")
        dest=self.root/"no-extra"
        with self.assertRaisesRegex(ValueError,"manifest does not describe"):
            restore_bundle(bad,dest)
        self.assertFalse(dest.exists())
        wrong=self.root/"changed-manifest.zip"
        with zipfile.ZipFile(bundle) as original,zipfile.ZipFile(wrong,"w") as copy:
            for entry in original.infolist():
                data=original.read(entry.filename)
                if entry.filename=="manifest.json":
                    doc=json.loads(data)
                    doc["files"][0]["sha256"]="0"*64
                    data=json.dumps(doc).encode()
                copy.writestr(entry,data)
        dest=self.root/"tamper-not-restored"
        with self.assertRaisesRegex(ValueError,"source bytes differ"):
            restore_bundle(wrong,dest)
        self.assertFalse(dest.exists())

    def test_import_symlinks_and_vault_inside_public_repo_rejected(self):
        original=self.receipt(0)
        nested=self.source/"nested"
        nested.mkdir()
        (nested/"agency-20261012T000000000000Z-"+"0"*16+".json.gz") if False else None
        try:
            (nested/original.name).symlink_to(original)
        except OSError:
            self.skipTest("symlinks unavailable in test environment")
        with self.assertRaisesRegex(ValueError,"linked or escaped"):
            ingest(self.vault,self.source)
        (nested/original.name).unlink()
        unsafe=Path(__file__).resolve().parents[1]/"unsafe-test-vault"
        with self.assertRaisesRegex(ValueError,"outside"):
            ingest(unsafe,self.source)
        self.assertFalse(unsafe.exists())

    def test_incremental_rollback_when_second_source_file_changes_while_copying(self):
        # A failed validation of the complete preflight cannot partially add files.
        self.receipt(0)
        changed=self.receipt(6)
        changed.write_bytes(changed.read_bytes()+b"changed")
        with self.assertRaisesRegex(ValueError,"checksum"):
            ingest(self.vault,self.source)
        self.assertFalse((self.vault/"receipts").exists())

    def test_cli_roundtrip_and_no_public_db_changes(self):
        self.receipt(0)
        def run(*args):
            return subprocess.run([sys.executable,"-m","fire_public.agency_vault",*args],
                       capture_output=True,text=True)
        first=run("ingest","--vault",str(self.vault),"--input",str(self.source))
        self.assertEqual(first.returncode,0,first.stderr)
        self.assertEqual(json.loads(first.stdout)["new_original_receipts"],1)
        audit=run("verify","--vault",str(self.vault))
        self.assertEqual(audit.returncode,0,audit.stderr)
        backup=self.root/"backup.zip"
        self.assertEqual(run("export","--vault",str(self.vault),
                             "--output",str(backup)).returncode,0)
        restored=self.root/"restored"
        self.assertEqual(run("restore","--bundle",str(backup),
                             "--vault",str(restored)).returncode,0)
        db=self.root/"history.sqlite3"
        self.assertEqual(run("rebuild","--vault",str(restored),
                             "--db",str(db)).returncode,0)
        store=HistoryStore(db)
        try:
            at=incident_at(store,"cwfis","CA-A",at="2026-10-12T01:00:00Z")
            self.assertEqual(at["availability"],"listed")
            self.assertIsNone(at["extinguishment_label"])
        finally:store.close()


if __name__=="__main__":
    unittest.main()
