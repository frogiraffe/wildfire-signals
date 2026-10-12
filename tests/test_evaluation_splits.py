"""Deterministic leakage and embargo regression checks."""
import unittest
from fire_public.evaluation_splits import holdout_split


def row(event, region, decision, label_time):
    return {"event_id": event, "region_id": region,
            "decision_at": decision, "label_available_at": label_time}


class SplitTests(unittest.TestCase):
    def test_temporal_cutoff_and_embargo(self):
        rows = [
            row("a", "A", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"),
            row("b", "A", "2026-10-09T12:00:00Z", "2026-10-09T14:00:00Z"),
            row("c", "A", "2026-10-10T00:00:00Z", "2026-10-11T00:00:00Z"),
        ]
        result = holdout_split(rows, test_start="2026-10-10T00:00:00Z", embargo_hours=24)
        self.assertEqual([r["event_id"] for r in result["train"]], ["a"])
        self.assertEqual([r["event_id"] for r in result["test"]], ["c"])
        self.assertEqual(result["excluded_by_reason"]["embargo_or_unavailable_outcome"], 1)

    def test_region_holdout_and_event_disjointness(self):
        rows = [
            row("train", "A", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"),
            row("shared", "A", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"),
            row("shared", "B", "2026-10-11T00:00:00Z", "2026-10-12T00:00:00Z"),
            row("historic", "B", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z"),
            row("future", "A", "2026-10-11T00:00:00Z", "2026-10-12T00:00:00Z"),
        ]
        result = holdout_split(rows, test_start="2026-10-10T00:00:00Z",
                               heldout_regions=["B"])
        self.assertEqual([r["event_id"] for r in result["train"]], ["train"])
        self.assertEqual([r["event_id"] for r in result["test"]], ["shared"])
        self.assertEqual(result["excluded_by_reason"]["repeated_test_event_removed_from_training"], 1)

    def test_reject_duplicate_and_naive_time(self):
        r = row("same", "A", "2026-10-01T00:00:00Z", "2026-10-02T00:00:00Z")
        with self.assertRaises(ValueError):
            holdout_split([r, r], test_start="2026-10-10T00:00:00Z")
        with self.assertRaises(ValueError):
            holdout_split([r], test_start="2026-10-10T00:00:00")

    def test_label_must_be_after_decision(self):
        r = row("x", "A", "2026-10-01T00:00:00Z", "2026-09-30T00:00:00Z")
        with self.assertRaises(ValueError):
            holdout_split([r], test_start="2026-10-10T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
