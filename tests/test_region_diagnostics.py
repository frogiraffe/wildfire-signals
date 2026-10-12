"""Offline tests for global satellite-candidate circle diagnostics."""
import unittest

from fire_public.region_diagnostics import distance_km, summarize_circle


class RegionDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.options = dict(latitude=0.0, longitude=179.9, radius_km=40,
                            as_of="2026-10-12T12:00:00Z", window_hours=24)

    def test_antimeridian_and_distinct_hours(self):
        events = [
            dict(latitude=0, longitude=-179.9, observed_at="2026-10-12T11:00:00Z",
                 sources=["NOAA-20"]),
            dict(latitude=0, longitude=-179.9, observed_at="2026-10-12T10:00:00Z",
                 sources=["NOAA-21"]),
            dict(latitude=0, longitude=170, observed_at="2026-10-12T11:00:00Z",
                 sources=["NOAA-21"]),
        ]
        result = summarize_circle(events, **self.options)
        self.assertEqual(result["candidate_cell_hours"], 2)
        self.assertEqual(result["distinct_observed_cells"], 1)
        self.assertEqual(result["cells_observed_in_multiple_hours"], 1)
        self.assertEqual(result["sensor_memberships"], {"NOAA-20": 1, "NOAA-21": 1})
        self.assertLess(distance_km(0, 179.9, 0, -179.9), 25)

    def test_window_excludes_future_and_old(self):
        events = [
            dict(latitude=0, longitude=179.9, observed_at="2026-10-12T12:01:00Z"),
            dict(latitude=0, longitude=179.9, observed_at="2026-10-11T11:59:00Z"),
        ]
        self.assertEqual(summarize_circle(events, **self.options)["candidate_cell_hours"], 0)

    def test_empty(self):
        result = summarize_circle([], **self.options)
        self.assertIsNone(result["last_observed_at"])
        self.assertEqual(result["sensor_memberships"], {})

    def test_invalid_coordinates_and_window(self):
        for overrides in ({"latitude": 91}, {"longitude": 181},
                          {"radius_km": 0}, {"window_hours": -1},
                          {"radius_km": float("nan")}):
            with self.subTest(overrides=overrides):
                self.assertRaises(ValueError, summarize_circle, [],
                                  **(self.options | overrides))

    def test_naive_times_rejected(self):
        with self.assertRaises(ValueError):
            summarize_circle([], **(self.options | {"as_of": "2026-10-12T12:00:00"}))


if __name__ == "__main__":
    unittest.main()
