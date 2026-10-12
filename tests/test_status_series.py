"""Retrospective agency statuses must not masquerade as live outcome labels."""
import tempfile
import unittest
from pathlib import Path

from fire_public.history import HistoryStore
from fire_public.status_series import analyze_status_series


class StatusSeriesTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.db = Path(temp.name) / "history.sqlite3"
        self.store = HistoryStore(self.db)
        self.addCleanup(self.store.close)
        self.base = {"subject_kind":"agency_incident","provider":"cwfis",
            "source_id":"CA-1","record_type":"incident_status",
            "source_url":"https://example.org/cwfis", "rights_url":"https://example.org/terms"}

    def add(self, start, end, status, captured="2026-10-12T02:00:00Z"):
        return self.store.append({**self.base,"observed_at":start,"captured_at":captured,
            "payload":{"stage_of_control_status":status,"record_end":end}})

    def analyze(self, at="2026-10-12T03:00:00Z"):
        return analyze_status_series(self.db,"CA-1",as_of=at)

    def test_retrospective_intervals_and_under_control_reversal(self):
        self.add("2019-05-13T00:00:00Z","2019-05-14T00:00:00Z","OC")
        self.add("2019-05-14T00:00:00Z","2019-05-15T00:00:00Z","UC")
        self.add("2019-05-15T00:00:00Z","2019-05-16T00:00:00Z","OC")
        self.assertEqual(self.analyze("2019-05-15T12:00:00Z")["record_count"],0)
        report = self.analyze()
        self.assertEqual(report["record_count"],3)
        self.assertEqual(report["transition_count"],2)
        self.assertEqual(report["control_to_out_of_control_count"],1)
        self.assertEqual(report["interval_hours_by_status"],{"OC":48,"UC":24})
        self.assertEqual(report["gaps"],[])
        self.assertTrue(report["retrospective_capture_only"])
        self.assertTrue(report["current_state_unknown"])

    def test_as_of_uses_latest_captured_correction_at_same_source_start(self):
        self.add("2019-05-13T00:00:00Z","2019-05-14T00:00:00Z","OC")
        self.add("2019-05-14T00:00:00Z","2019-05-15T00:00:00Z","UC")
        self.add("2019-05-14T00:00:00Z","2019-05-15T00:00:00Z","BH",
                 captured="2026-10-12T04:00:00Z")
        self.assertEqual(self.analyze()["intervals"][1]["status"],"UC")
        self.assertEqual(self.analyze("2026-10-12T05:00:00Z")["intervals"][1]["status"],"BH")

    def test_gaps_and_overlaps_are_reported_without_filling_them(self):
        self.add("2019-05-13T00:00:00Z","2019-05-14T00:00:00Z","OC")
        self.add("2019-05-14T06:00:00Z","2019-05-15T00:00:00Z","BH")
        self.add("2019-05-14T23:00:00Z","2019-05-16T00:00:00Z","UC")
        report = self.analyze()
        self.assertEqual(report["gaps"][0]["hours"],6)
        self.assertEqual(report["overlaps"][0]["hours"],1)
        self.assertTrue(report["current_state_unknown"])

    def test_conflicting_versions_with_same_receipt_time_are_ambiguous(self):
        self.add("2019-05-13T00:00:00Z","2019-05-14T00:00:00Z","OC")
        self.add("2019-05-13T00:00:00Z","2019-05-14T00:00:00Z","UC")
        with self.assertRaisesRegex(ValueError,"ambiguous"):
            self.analyze()


if __name__ == "__main__":
    unittest.main()
