"""Tests for strict holdout eligibility; synthetic fixtures are not wildfire labels."""
import unittest

from fire_public.holdout_audit import audit_holdout


def item(unit, event, region, date, split, label):
    return {
        "sampling_unit_id": unit, "event_id": event, "region_id": region,
        "feature_as_of": date, "feature_latest_available_at": date,
        "label_available_at": date, "split": split, "label": label,
    }


def valid():
    return [
        item("a", "A", "north", "2024-01-01T00:00:00Z", "train", 0),
        item("b", "B", "north", "2024-01-02T00:00:00Z", "train", 1),
        item("c", "C", "south", "2025-01-01T00:00:00Z", "test", 0),
        item("d", "D", "south", "2025-01-02T00:00:00Z", "test", 1),
    ]


class HoldoutAuditTests(unittest.TestCase):
    def test_clean_partition_is_eligible_but_never_measures_skill(self):
        result = audit_holdout(valid(), embargo_hours=24)
        self.assertTrue(result["eligible_for_holdout_evaluation"])
        self.assertIsNone(result["measured_skill"])

    def test_event_overlap(self):
        data = valid()
        data[2]["event_id"] = "A"
        self.assertIn("event_overlap", audit_holdout(data)["failed_gates"])

    def test_region_overlap(self):
        data = valid()
        data[2]["region_id"] = "north"
        self.assertIn("region_overlap", audit_holdout(data)["failed_gates"])

    def test_future_feature(self):
        data = valid()
        data[0]["feature_latest_available_at"] = "2024-01-03T00:00:00Z"
        self.assertIn("future_feature_leakage", audit_holdout(data)["failed_gates"])

    def test_missing_feature_availability(self):
        data = valid()
        del data[0]["feature_latest_available_at"]
        self.assertIn("missing_feature_availability", audit_holdout(data)["failed_gates"])

    def test_temporal_overlap(self):
        data = valid()
        data[2]["feature_as_of"] = "2024-01-01T00:00:00Z"
        self.assertIn("temporal_or_embargo_overlap", audit_holdout(data)["failed_gates"])

    def test_duplicate_and_missing_label(self):
        data = valid()
        data[2]["sampling_unit_id"] = "a"
        data[2]["label"] = None
        self.assertIn("duplicate_sampling_unit", audit_holdout(data)["failed_gates"])
        self.assertIn("unknown_or_invalid_label", audit_holdout(data)["failed_gates"])

    def test_missing_class(self):
        data = valid()
        data[3]["label"] = 0
        self.assertIn("missing_class_test", audit_holdout(data)["failed_gates"])

    def test_reject_naive_datetime(self):
        data = valid()
        data[0]["feature_as_of"] = "2024-01-01T00:00:00"
        with self.assertRaises(ValueError):
            audit_holdout(data)

    def test_bad_embargo(self):
        with self.assertRaises(ValueError):
            audit_holdout(valid(), embargo_hours=float("nan"))


if __name__ == "__main__":
    unittest.main()
