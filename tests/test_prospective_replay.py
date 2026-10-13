"""As-of historical research console tests using synthetic source receipts only."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

from fire_public.analysis_receipt import build_receipt, write_receipt
from fire_public.history import HistoryStore
from fire_public.receipt_history import import_receipts
from fire_public.prospective_replay import (replay, open_archive, offline_html,
                                            _write_private)


class ProspectiveTimeMachineTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.path=self.root/"history.sqlite3"
        self.store=HistoryStore(self.path)
        self.addCleanup(self.store.close)
        self.receipts=self.root/"receipts"

    def add(self, hour: int, *, agency="complete", listed=True, status="OC",
            name="Archive-only example", modified_at=None, last_seen_at=None, nifc=False):
        scan=f"2026-10-12T{hour:02d}:17:00Z"
        capture=f"2026-10-12T{hour:02d}:18:00Z"
        incident={"kind":"agency_incident","provider":"cwfis","official_id":"CA-1",
                  "name":name,"incident_kind":"active_wildland_fire",
                  "latitude":45.0,"longitude":-115.0,
                  "modified_at":modified_at or scan,
                  "agency_status":status,"last_seen_at":last_seen_at or scan}
        status_rows=[{"key":"cwfis","status":agency},{"key":"nifc_wfigs","status":"complete"}]
        entries=[incident] if listed else []
        if nifc:
            entries.append({**incident,"provider":"nifc_wfigs","official_id":"IRWIN-1",
                            "agency_status":None,"name":"Different agency"})
        snapshot={"manifest":{"schema_version":1,"last_scan_at":scan,
                   "data_status":"fresh" if agency=="complete" else "partial",
                   "truncated":False,"source_errors":[] if agency=="complete" else ["cwfis"]},
                  "sources":status_rows,"incidents":entries,"events":[],"matches":[]}
        raw,_=build_receipt(snapshot,captured_at=capture,run_id=str(100+hour),
                            head_sha="a"*40,snapshot_key="snapshot:"+"b"*64)
        return write_receipt(self.receipts,raw,scan_at=scan)

    def imported(self):
        import_receipts(self.store,self.receipts)
        self.store.connection.commit()
        return open_archive(self.path)

    def test_as_of_replay_preserves_source_gaps_and_status_reversal(self):
        self.add(0)
        self.add(6,agency="failed",listed=True) # Prior fallback is not a new confirmation.
        self.add(12,listed=False)
        self.add(18,status="UC")
        db=self.imported()
        self.addCleanup(db.close)
        pre=replay(db,at="2026-10-12T00:17:59Z")
        self.assertEqual(pre["known_source_identities"],0)
        self.assertEqual(pre["source_scan_rows"],0)
        early=replay(db,at="2026-10-12T03:00:00Z")
        self.assertEqual(early["agency_scan_count"],1)
        self.assertEqual(early["known_source_identities"],1)
        self.assertEqual(early["cases"][0]["timeline"][-1]["agency_status"],"OC")
        self.assertEqual(len(early["cases"][0]["timeline"]),1)
        failed=replay(db,at="2026-10-12T09:00:00Z",provider="cwfis")
        self.assertEqual(failed["agency_scan_count"],2)
        self.assertEqual(failed["cases"][0]["timeline"][-1]["availability"],"source_unavailable")
        self.assertEqual(failed["cases"][0]["timeline"][-1]["source_status"],"failed")
        self.assertIsNone(failed["cases"][0]["timeline"][-1]["agency_status"])
        absent=replay(db,at="2026-10-12T15:00:00Z",provider="cwfis")
        self.assertEqual(absent["cases"][0]["timeline"][-1]["availability"],
                         "not_listed_in_complete_scan")
        self.assertEqual(absent["cases"][0]["last_listed_at"],
                         "2026-10-12T00:18:00+00:00")
        recent=replay(db,at="2026-10-12T23:00:00Z",provider="cwfis")
        trace=recent["cases"][0]["timeline"]
        self.assertEqual([r["availability"] for r in trace],
              ["listed","source_unavailable","not_listed_in_complete_scan","listed"])
        self.assertEqual(trace[-1]["agency_status"],"UC")
        self.assertEqual(recent["cases"][0]["observed_state_changes"],3)
        self.assertTrue(all(row["extinguishment_label"] is None for row in trace))
        self.assertEqual(recent["verified_extinguishment_labels"],0)
        self.assertFalse(recent["forecast_skill_measured"])

    def test_other_agency_identity_separate_even_when_record_nearby(self):
        self.add(0,nifc=True)
        db=self.imported()
        self.addCleanup(db.close)
        result=replay(db,at="2026-10-12T03:00:00Z")
        self.assertEqual(result["known_source_identities"],2)
        self.assertEqual(len({row["source_identity"] for row in result["cases"]}),2)
        self.assertEqual(result["verified_cross_provider_event_links"],0)
        selected=replay(db,at="2026-10-12T03:00:00Z",
                        provider="nifc_wfigs",official_id="IRWIN-1")
        self.assertEqual(len(selected["cases"]),1)
        self.assertEqual(selected["cases"][0]["provider"],"nifc_wfigs")
        self.assertEqual(selected["agency_scan_count"],1)
        with self.assertRaisesRegex(ValueError,"requires"):
            replay(db,at="2026-10-12T03:00:00Z",official_id="IRWIN-1")
        with self.assertRaises(ValueError):
            replay(db,at="2026-10-12T03:00:00Z",provider="madeup")

    def test_stable_incident_payload_with_distinct_capture_run_provenance(self):
        # The source payload is identical, but different Actions run URLs are
        # deliberately distinct archival receipts (not duplicate evidence).
        time="2026-10-12T00:17:00Z"
        self.add(0,modified_at=time,last_seen_at=time)
        self.add(6,modified_at=time,last_seen_at=time)
        db=self.imported()
        self.addCleanup(db.close)
        report=replay(db,at="2026-10-12T09:00:00Z",provider="cwfis")
        self.assertEqual(len(report["cases"][0]["timeline"]),2)
        self.assertEqual(self.store.connection.execute(
            "SELECT COUNT(*) FROM observations WHERE provider='cwfis'").fetchone()[0],2)
        self.assertEqual(report["cases"][0]["timeline"][0]["source_modified_at"],time)
        self.assertEqual(report["cases"][0]["timeline"][1]["source_modified_at"],time)

    def test_report_does_not_import_receipts_received_after_selected_time(self):
        self.add(0,name="INITIAL")
        self.add(18,name="FUTURE")
        db=self.imported()
        self.addCleanup(db.close)
        result=replay(db,at="2026-10-12T04:00:00Z")
        self.assertEqual(result["cases"][0]["latest_known_name"],"INITIAL")
        self.assertNotIn("FUTURE",json.dumps(result))
        self.assertEqual(result["agency_scan_count"],1)

    def test_missing_original_observation_fails_closed(self):
        self.add(0)
        self.imported().close()
        self.store.connection.execute("DELETE FROM observations")
        self.store.connection.commit()
        db=open_archive(self.path)
        self.addCleanup(db.close)
        with self.assertRaisesRegex(ValueError,"missing/ambiguous"):
            replay(db,at="2026-10-12T04:00:00Z")

    def test_source_status_contradiction_cannot_manufacture_fresh_confirmations(self):
        self.add(0)
        self.imported().close()
        self.store.connection.execute("""
            UPDATE receipt_sources SET status='failed' WHERE provider='cwfis'
        """)
        self.store.connection.commit()
        db=open_archive(self.path)
        self.addCleanup(db.close)
        with self.assertRaisesRegex(ValueError,"failed source"):
            replay(db,at="2026-10-12T04:00:00Z")

    def test_offline_html_escapes_malicious_agency_names_and_prevents_remote_scripts(self):
        self.add(0,name='</script><img src=x onerror=alert("injected")>')
        db=self.imported()
        self.addCleanup(db.close)
        report=replay(db,at="2026-10-12T04:00:00Z")
        page=offline_html(report)
        self.assertIn("Content-Security-Policy",page)
        self.assertIn("connect-src &#x27;none&#x27;",page)
        self.assertNotIn("</script><img",page)
        self.assertNotIn("<img src=x",page)
        self.assertIn('id="moment"',page)
        self.assertIn("AgencyReplay.mount",page)
        code=re.search(r"<script>(.*?)</script>",page,re.DOTALL).group(1)
        csp=re.search(r"script-src &#x27;sha256-([^&#]+)&#x27;",page).group(1)
        self.assertEqual(base64.b64encode(hashlib.sha256(code.encode()).digest()).decode(),csp)
        with self.assertRaisesRegex(ValueError,"no verified"):
            offline_html(dict(report,verified_extinguishment_labels=1))

    def test_read_only_open_and_private_output_refuse_git_or_overwrite(self):
        self.add(0)
        db=self.imported()
        self.addCleanup(db.close)
        report=replay(db,at="2026-10-12T04:00:00Z")
        dest=self.root/"new-private"
        _write_private(dest,report)
        self.assertEqual((dest/"index.html").stat().st_mode&0o777,0o600)
        self.assertEqual(dest.stat().st_mode&0o777,0o700)
        self.assertEqual(json.loads((dest/"evidence.json").read_text())["known_source_identities"],1)
        with self.assertRaisesRegex(ValueError,"new output"):
            _write_private(dest,report)
        git=Path(__file__).resolve().parents[1]/"test-output-unsafe"
        with self.assertRaisesRegex(ValueError,"outside Git"):
            _write_private(git,report)
        self.assertFalse(git.exists())
        with self.assertRaisesRegex(ValueError,"outside"):
            open_archive(Path(__file__).resolve().parents[1]/"README.md")
        with self.assertRaises(ValueError):
            open_archive(self.root/"does-not-exist.sqlite3")

    def test_cli_outputs_and_rejects_incomplete_source_population(self):
        self.add(0)
        self.imported().close()
        root=self.root/"cli-bundle"
        args=[sys.executable,"-m","fire_public.prospective_replay",
              "--db",str(self.path),"--output-dir",str(root),
              "--provider","cwfis","--official-id","CA-1",
              "--at","2026-10-12T04:00:00Z"]
        run=subprocess.run(args,capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(json.loads(run.stdout)["cases"],1)
        self.assertTrue((root/"index.html").is_file())
        self.assertNotEqual(subprocess.run(args,capture_output=True).returncode,0)

    def test_older_archive_with_no_prospective_receipts_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"no imported prospective"):
            open_archive(self.path)


if __name__=="__main__":
    unittest.main()
