"""Prospective receipts preserve known presence and unknown source intervals."""
import tempfile
import unittest
from pathlib import Path

from fire_public.analysis_receipt import build_receipt, write_receipt
from fire_public.history import HistoryStore
from fire_public.receipt_history import import_receipts, incident_at


class ReceiptHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = HistoryStore(self.root / "history.sqlite3")
        self.addCleanup(self.store.close)
        self.receipts = self.root / "receipts"

    def add(self, hour, *, status="complete", listed=True, agency_status="OC"):
        scan = f"2026-10-12T{hour:02d}:17:00+00:00"
        capture = f"2026-10-12T{hour:02d}:18:00+00:00"
        row = {"kind":"agency_incident","provider":"cwfis","official_id":"CA-1",
               "name":"Example","incident_kind":"active_wildland_fire",
               "latitude":55.0,"longitude":-110.0,"modified_at":scan,
               "agency_status":agency_status,"last_seen_at":scan}
        snapshot = {"manifest":{"schema_version":1,"last_scan_at":scan,
                    "data_status":"fresh" if status == "complete" else "partial",
                    "source_errors":[] if status == "complete" else ["cwfis"],
                    "truncated":False},
                    "sources":[{"key":"nifc_wfigs","status":"complete"},
                               {"key":"cwfis","status":status}],
                    "incidents":[row] if listed else [],"events":[],"matches":[]}
        payload,_ = build_receipt(snapshot,captured_at=capture,run_id=str(100 + hour),
                                  head_sha="a" * 40,snapshot_key="snapshot:" + "b" * 64)
        write_receipt(self.receipts,payload,scan_at=scan)

    def test_presence_disappearance_and_failed_source_stay_distinct(self):
        self.add(0)
        self.add(6,status="failed",listed=True)  # Collector fallback is stale.
        self.add(12,listed=False)
        self.assertEqual(import_receipts(self.store,self.receipts)["imported_scans"],3)
        first = incident_at(self.store,"cwfis","CA-1",at="2026-10-12T03:00:00Z")
        self.assertEqual(first["availability"],"listed")
        failed = incident_at(self.store,"cwfis","CA-1",at="2026-10-12T09:00:00Z")
        self.assertEqual(failed["availability"],"source_unavailable")
        self.assertEqual(failed["source_status"],"failed")
        absent = incident_at(self.store,"cwfis","CA-1",at="2026-10-12T15:00:00Z")
        self.assertEqual(absent["availability"],"not_listed_in_complete_scan")
        self.assertIsNone(absent["extinguishment_label"])
        self.assertEqual(absent["last_listed_at"],"2026-10-12T00:18:00+00:00")
        self.assertEqual(len(self.store.as_of("2026-10-12T09:00:00Z","cwfis:CA-1")),1)
        self.assertEqual(import_receipts(self.store,self.receipts)["imported_scans"],0)

    def test_later_status_is_not_available_at_earlier_decision_time(self):
        self.add(0,agency_status="OC")
        self.add(6,agency_status="UC")
        import_receipts(self.store,self.receipts)
        self.assertEqual(incident_at(self.store,"cwfis","CA-1",
                         at="2026-10-12T03:00:00Z")["agency_status"],"OC")
        self.assertEqual(incident_at(self.store,"cwfis","CA-1",
                         at="2026-10-12T09:00:00Z")["agency_status"],"UC")
        self.assertEqual(incident_at(self.store,"cwfis","CA-1",
                         at="2026-10-12T00:17:30Z")["availability"],"no_receipt_yet")

    def test_corrupted_later_receipt_rolls_back_whole_batch(self):
        self.add(0)
        self.add(6)
        later = sorted(self.receipts.glob("*.gz"))[-1]
        later.write_bytes(later.read_bytes() + b"tamper")
        with self.assertRaisesRegex(ValueError,"checksum"):
            import_receipts(self.store,self.receipts)
        self.assertEqual(self.store.as_of("2026-10-13T00:00:00Z","cwfis:CA-1"),[])

    def test_same_scan_with_changed_artifact_is_rejected_after_import(self):
        self.add(0)
        self.assertEqual(import_receipts(self.store,self.receipts)["imported_scans"],1)
        for path in self.receipts.glob("*.gz"):
            path.unlink()
        self.add(0,agency_status="UC")
        with self.assertRaisesRegex(ValueError,"conflicting agency scan receipt"):
            import_receipts(self.store,self.receipts)
        self.assertEqual(incident_at(self.store,"cwfis","CA-1",
                         at="2026-10-12T03:00:00Z")["agency_status"],"OC")

    def test_import_respects_callers_existing_transaction(self):
        self.add(0)
        self.store.connection.execute("BEGIN")
        import_receipts(self.store,self.receipts)
        self.store.connection.rollback()
        self.assertEqual(self.store.as_of("2026-10-13T00:00:00Z","cwfis:CA-1"),[])


if __name__ == "__main__":
    unittest.main()
