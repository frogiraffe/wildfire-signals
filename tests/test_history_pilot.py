"""Official source pilot parses historical facts without time-travel claims."""
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from fire_public.history_pilot import cwfis_records, nifc_perimeter_record, replay_pilot, run_pilot
from fire_public.history import HistoryStore


CAPTURED = "2026-10-12T15:00:00Z"


class HistoryPilotTests(unittest.TestCase):
    def test_cwfis_status_intervals_remain_distinct_and_backfilled(self):
        source = {"type": "FeatureCollection", "features": [
            {"properties": {"national_fire_id": "0_SK_003464", "stage_of_control_status": "UC",
                            "record_start": "2019-05-15T15:29:00Z", "record_end": "2019-05-19T15:29:00Z",
                            "latitude": 53.7, "longitude": -107.0, "fire_size": 4.0}},
            {"properties": {"national_fire_id": "0_SK_003464", "stage_of_control_status": "OC",
                            "record_start": "2019-05-19T15:29:00Z", "record_end": "2019-05-21T23:29:00Z",
                            "latitude": 53.7, "longitude": -107.0, "fire_size": 5.0}}]}
        rows = cwfis_records(source, expected_id="0_SK_003464", captured_at=CAPTURED,
                             source_url="https://example.org/wfs")
        self.assertEqual([x["payload"]["stage_of_control_status"] for x in rows], ["UC", "OC"])
        self.assertEqual(rows[0]["observed_at"], "2019-05-15T15:29:00Z")
        self.assertEqual(rows[0]["captured_at"], CAPTURED)
        self.assertEqual(rows[0]["subject_kind"], "agency_incident")
        self.assertEqual(rows[0]["record_type"], "incident_status")

    def test_volatile_wfs_feature_id_does_not_create_a_new_status_observation(self):
        payload = {"national_fire_id": "0_SK_003423", "stage_of_control_status": "UC",
                   "record_start": "2019-05-02T16:12:00Z", "record_end": "2019-05-08T19:29:00Z"}
        first = {"type": "FeatureCollection", "features": [{"id": "server-a", "properties": payload}]}
        second = {"type": "FeatureCollection", "features": [{"id": "server-b", "properties": payload}]}
        with tempfile.TemporaryDirectory() as temp:
            store = HistoryStore(Path(temp) / "stable.sqlite3")
            self.addCleanup(store.close)
            a = cwfis_records(first, expected_id="0_SK_003423", captured_at=CAPTURED,
                              source_url="https://example.org/wfs")[0]
            b = cwfis_records(second, expected_id="0_SK_003423",
                              captured_at="2026-10-12T16:00:00Z",
                              source_url="https://example.org/wfs")[0]
            self.assertEqual(store.append(a), store.append(b))

    def test_nifc_perimeter_keeps_esri_geometry_and_late_capture(self):
        source = {"features": [{"attributes": {
            "poly_IRWINID": "{EFB046E9-CE8C-4DE6-87A7-E824C33AE187}",
            "poly_PolygonDateTime": 1668840740000, "poly_IncidentName": "PULLEN CREEK",
            "attr_IncidentTypeCategory": "WF", "attr_FireOutDateTime": 1672264800000},
            "geometry": {"rings": [[[-100, 40], [-99, 40], [-99, 41], [-100, 40]]]} }]}
        row = nifc_perimeter_record(source,
              expected_id="{EFB046E9-CE8C-4DE6-87A7-E824C33AE187}",
              captured_at=CAPTURED, source_url="https://example.org/query")
        self.assertEqual(row["record_type"], "perimeter_observation")
        self.assertEqual(row["payload"]["geometry_format"], "esri_json_epsg4326")
        self.assertEqual(row["payload"]["geometry"]["rings"][0][0], [-100, 40])
        self.assertEqual(row["captured_at"], CAPTURED)
        self.assertEqual(row["payload"]["perimeter_role"], "retrospective_outcome")

    def test_pilot_rejects_wrong_event_or_missing_geometry(self):
        with self.assertRaises(ValueError):
            cwfis_records({"type": "FeatureCollection", "features": [
                {"properties": {"national_fire_id": "other"}}]}, expected_id="wanted",
                captured_at=CAPTURED, source_url="https://example.org/wfs")
        with self.assertRaises(ValueError):
            nifc_perimeter_record({"features": [{"attributes": {
                "poly_IRWINID": "wanted", "poly_PolygonDateTime": 1668840740000,
                "attr_IncidentTypeCategory": "WF"}}]}, expected_id="wanted",
                captured_at=CAPTURED, source_url="https://example.org/query")

    def test_raw_source_manifest_rebuilds_archive_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            raw_dir = Path(temp) / "raw"
            raw_dir.mkdir()
            source = {"type": "FeatureCollection", "features": [{"id": "feature-1",
                "properties": {"national_fire_id": "0_SK_003423",
                               "stage_of_control_status": "UC",
                               "record_start": "2019-05-02T16:12:00Z",
                               "record_end": "2019-05-08T19:29:00Z"}}]}
            raw = json.dumps(source).encode()
            digest = hashlib.sha256(raw).hexdigest()
            path = raw_dir / f"{digest}.json.gz"
            path.write_bytes(gzip.compress(raw, mtime=0))
            (raw_dir / "pilot-manifest.json").write_text(json.dumps({
                "captured_at": CAPTURED,
                "samples": [{"event_key": "cwfis:0_SK_003423",
                             "source_url": "https://example.org/wfs",
                             "source_response_sha256": digest, "record_count": 1}]}))
            db = Path(temp) / "restored.sqlite3"
            self.assertEqual(replay_pilot(raw_dir, db)["restored_records"], 1)
            store = HistoryStore(db)
            self.addCleanup(store.close)
            self.assertEqual(len(store.as_of(CAPTURED, "cwfis:0_SK_003423")), 1)
            self.assertEqual(store.as_of("2019-05-03T00:00:00Z", "cwfis:0_SK_003423"), [])
            with self.assertRaises(FileExistsError):
                replay_pilot(raw_dir, db)
            path.write_bytes(gzip.compress(b'{}', mtime=0))
            with self.assertRaises(ValueError):
                replay_pilot(raw_dir, Path(temp) / "corrupt.sqlite3")

    def test_fresh_pilot_does_not_overwrite_existing_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "pilot.sqlite3"
            db.write_bytes(b"user data")
            with self.assertRaises(FileExistsError):
                run_pilot(db, Path(temp) / "raw")
            self.assertEqual(db.read_bytes(), b"user data")


if __name__ == "__main__":
    unittest.main()
