"""Historical evidence must be replayable without future information."""
import tempfile
import unittest
from pathlib import Path

from fire_public.history import HistoryStore, archive_snapshot


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "history.sqlite3"
        self.store = HistoryStore(self.path)
        self.addCleanup(self.store.close)

    def test_append_only_as_of_excludes_later_perimeter_and_keeps_corrections(self):
        base = {"subject_kind": "agency_incident", "provider": "nifc_wfigs",
                "source_id": "irwin-1", "record_type": "incident_status",
                "observed_at": "2026-10-01T12:00:00Z",
                "source_url": "https://example.org/incident/1",
                "rights_url": "https://example.org/license"}
        self.store.append({**base, "captured_at": "2026-10-01T12:05:00Z",
                           "payload": {"status": "active"}})
        self.store.append({**base, "captured_at": "2026-10-03T12:05:00Z",
                           "payload": {"status": "controlled"}})
        self.store.append({**base, "record_type": "perimeter_observation",
                           "captured_at": "2026-10-04T00:00:00Z",
                           "observed_at": "2026-10-01T13:00:00Z",
                           "payload": {"geometry": {"type": "Polygon", "coordinates": []}}})
        earlier = self.store.as_of("2026-10-01T18:00:00Z", "nifc_wfigs:irwin-1")
        self.assertEqual([row["payload"]["status"] for row in earlier], ["active"])
        self.assertEqual(len(self.store.as_of("2026-10-05T00:00:00Z", "nifc_wfigs:irwin-1")), 3)

    def test_same_record_deduplicates_and_changed_payload_appends(self):
        record = {"subject_kind": "agency_incident", "provider": "cwfis",
                  "source_id": "AB-17", "record_type": "incident_status",
                  "observed_at": "2026-10-01T12:00:00Z",
                  "captured_at": "2026-10-01T12:05:00Z",
                  "source_url": "https://example.org/fire/17",
                  "rights_url": "https://example.org/license",
                  "payload": {"status": "OC"}}
        first = self.store.append(record)
        self.assertEqual(self.store.append(record), first)
        second = self.store.append({**record, "payload": {"status": "BH"}})
        self.assertNotEqual(second, first)
        self.assertEqual(len(self.store.as_of("2026-10-02T00:00:00Z", "cwfis:AB-17")), 2)

    def test_corrected_source_rights_append_a_new_provenance_version(self):
        record = {"subject_kind": "agency_incident", "provider": "cwfis",
                  "source_id": "AB-17", "record_type": "incident_status",
                  "observed_at": "2026-10-01T12:00:00Z",
                  "captured_at": "2026-10-01T12:05:00Z",
                  "source_url": "https://example.org/fire/17",
                  "rights_url": "https://example.org/license-old",
                  "payload": {"status": "OC"}}
        first = self.store.append(record)
        second = self.store.append({**record, "rights_url": "https://example.org/license-new",
                                    "captured_at": "2026-10-01T13:05:00Z"})
        self.assertNotEqual(first, second)

    def test_candidate_is_not_promoted_to_agency_incident(self):
        self.store.append({"subject_kind": "satellite_candidate", "provider": "firms",
                           "source_id": "cell-1", "record_type": "thermal_observation",
                           "observed_at": "2026-10-01T12:00:00Z",
                           "captured_at": "2026-10-01T13:00:00Z",
                           "source_url": "https://firms.modaps.eosdis.nasa.gov/",
                           "rights_url": "https://firms.modaps.eosdis.nasa.gov/",
                           "payload": {"detection_count": 2}})
        self.assertEqual(self.store.as_of("2026-10-02T00:00:00Z", "firms:cell-1")[0]["subject_kind"],
                         "satellite_candidate")
        self.assertEqual(self.store.as_of("2026-10-02T00:00:00Z", "nifc_wfigs:cell-1"), [])

    def test_rejects_naive_or_inconsistent_times_and_nonfinite_payload(self):
        record = {"subject_kind": "agency_incident", "provider": "cwfis",
                  "source_id": "x", "record_type": "incident_status",
                  "observed_at": "2026-10-01T12:00:00Z",
                  "captured_at": "2026-10-01T12:01:00Z",
                  "source_url": "https://example.org/x", "rights_url": "https://example.org/license",
                  "payload": {"status": "OC"}}
        with self.assertRaises(ValueError):
            self.store.append({**record, "captured_at": "2026-10-01T12:01:00"})
        with self.assertRaises(ValueError):
            self.store.append({**record, "observed_at": "2026-10-02T12:00:00Z"})
        with self.assertRaises(ValueError):
            self.store.append({**record, "payload": {"value": float("nan")}})

    def test_archives_snapshot_provenance_without_confirming_candidate(self):
        snapshot = {
            "manifest": {"schema_version": 1, "last_scan_at": "2026-10-01T12:00:00Z",
                         "source_errors": ["cwfis"], "data_status": "partial"},
            "events": [{"kind": "satellite_candidate", "event_id": "firms-cell-1",
                        "observed_at": "2026-10-01T11:30:00Z", "detection_count": 2,
                        "sources": ["VIIRS_NOAA20_NRT"]}],
            "incidents": [{"kind": "agency_incident", "provider": "nifc_wfigs",
                           "official_id": "irwin-1", "modified_at": "2026-10-01T10:00:00Z",
                           "last_seen_at": "2026-10-01T12:00:00Z", "name": "Example"}],
            "matches": [{"event_id": "firms-cell-1", "official_id": "irwin-1",
                         "status": "provisional"}], "sources": []}
        count = archive_snapshot(self.store, snapshot, captured_at="2026-10-01T13:00:00Z",
                                 source_url="https://example.org/api/snapshot",
                                 rights_by_provider={"firms": "https://example.org/nasa-terms",
                                                     "nifc_wfigs": "https://example.org/nifc-terms"})
        self.assertEqual(count, 2)
        self.assertEqual(self.store.as_of("2026-10-01T12:30:00Z", "nifc_wfigs:irwin-1"), [])
        self.assertEqual(len(self.store.as_of("2026-10-01T13:00:00Z", "nifc_wfigs:irwin-1")), 1)
        self.assertEqual(self.store.as_of("2026-10-01T13:00:00Z", "firms:firms-cell-1")[0]
                         ["subject_kind"], "satellite_candidate")
        self.assertEqual(self.store.scan_gaps()[0]["source_errors"], ["cwfis"])
        self.assertEqual(archive_snapshot(self.store, snapshot, captured_at="2026-10-01T13:00:00Z",
                         source_url="https://example.org/api/snapshot",
                         rights_by_provider={"firms": "https://example.org/nasa-terms",
                                             "nifc_wfigs": "https://example.org/nifc-terms"}), 0)

    def test_malformed_candidate_rolls_back_whole_snapshot_import(self):
        snapshot = {"manifest": {"schema_version": 1,
                                 "last_scan_at": "2026-10-01T12:00:00Z"},
                    "incidents": [{"kind": "agency_incident", "provider": "cwfis",
                                   "official_id": "CA-1", "modified_at": "2026-10-01T11:00:00Z"}],
                    "events": [{"kind": "satellite_candidate", "event_id": "cell-1",
                                "observed_at": "2026-10-02T12:00:00Z"}]}
        with self.assertRaises(ValueError):
            archive_snapshot(self.store, snapshot, captured_at="2026-10-01T13:00:00Z",
                             source_url="https://example.org/api/snapshot",
                             rights_by_provider={"cwfis": "https://example.org/license",
                                                 "firms": "https://example.org/terms"})
        self.assertEqual(self.store.as_of("2026-10-03T00:00:00Z", "cwfis:CA-1"), [])
        self.assertEqual(self.store.scan_gaps(), [])


if __name__ == "__main__":
    unittest.main()
