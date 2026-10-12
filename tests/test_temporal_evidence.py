"""As-of and overlapping-snapshot regression tests for global temporal evidence."""
import unittest

from fire_public.temporal_evidence import regional_timeline


def snapshot(scan, events, status="complete", errors=None):
    return {"manifest": {"last_scan_at": scan, "data_status": status,
                         "source_errors": errors or []}, "events": events}


def event(event_id, at, lon=179.9):
    return {"event_id": event_id, "observed_at": at, "latitude": 0.0,
            "longitude": lon, "sources": ["NOAA-20"]}


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.kw = dict(latitude=0, longitude=179.9, radius_km=50,
                       as_of="2026-10-12T12:00:00Z", window_hours=24,
                       bucket_hours=6)

    def test_repeated_snapshots_are_not_new_events(self):
        first = event("one", "2026-10-12T09:00:00Z", -179.9)
        second = event("two", "2026-10-12T02:00:00Z")
        rows = [
            snapshot("2026-10-12T10:00:00Z", [first]),
            snapshot("2026-10-12T11:00:00Z", [first, second],
                     "partial", ["NOAA-21"]),
        ]
        result = regional_timeline(rows, **self.kw)
        self.assertEqual(result["candidate_observations"], 2)
        self.assertEqual([r["candidate_observations"] for r in result["buckets_newest_first"]],
                         [1, 1, 0, 0])
        self.assertEqual(result["latest_source_errors"], ["NOAA-21"])

    def test_future_snapshot_and_future_observation_are_excluded(self):
        rows = [snapshot("2026-10-12T11:00:00Z",
                         [event("future-observed", "2026-10-12T11:30:00Z"),
                          event("valid", "2026-10-12T10:00:00Z")]),
                snapshot("2026-10-12T13:00:00Z",
                         [event("late", "2026-10-12T09:00:00Z")])]
        result = regional_timeline(rows, **self.kw)
        self.assertEqual(result["candidate_observations"], 1)
        self.assertEqual(result["snapshot_count"], 1)

    def test_missing_snapshots_do_not_claim_zero_fires(self):
        result = regional_timeline([], **self.kw)
        self.assertEqual(result["candidate_observations"], 0)
        self.assertIsNone(result["latest_data_status"])
        self.assertIsNone(result["latest_source_errors"])

    def test_invalid_bucket(self):
        with self.assertRaises(ValueError):
            regional_timeline([], **(self.kw | {"bucket_hours": 0}))

    def test_idless_fallback_is_deduplicated(self):
        row = event(None, "2026-10-12T09:00:00Z")
        result = regional_timeline(
            [snapshot("2026-10-12T10:00:00Z", [row]),
             snapshot("2026-10-12T11:00:00Z", [row])], **self.kw)
        self.assertEqual(result["candidate_observations"], 1)


if __name__ == "__main__":
    unittest.main()
