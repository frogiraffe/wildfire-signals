"""Offline fixtures for historical base-rate evaluation. NOT wildfire outcomes."""
import unittest

from fire_public.historical_baseline import historical_rate_experiment


def case(event, at, label, region="A", available=None):
    return {"event_id": event, "region_id": region,
            "decision_at": at,
            "label_available_at": available or "2026-10-11T00:00:00Z",
            "label": label, "label_source": "fixture-independent-agency",
            "label_source_id": event}


class HistoricalBaselineTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            case("train1", "2026-08-01T00:00:00Z", 1,
                 available="2026-08-02T00:00:00Z"),
            case("train2", "2026-08-01T00:00:00Z", 0,
                 available="2026-08-02T00:00:00Z"),
            case("test1", "2026-10-10T00:00:00Z", 1),
            case("test2", "2026-10-10T00:00:00Z", 0),
        ]

    def test_training_rate_and_holdout(self):
        result = historical_rate_experiment(
            self.rows, test_start="2026-10-01T00:00:00Z")
        self.assertEqual((result["train_n"], result["test_n"]), (2, 2))
        self.assertEqual(result["fit_rate"], 0.5)
        self.assertAlmostEqual(result["evaluation"]["brier_score"], 0.25)

    def test_test_outcomes_do_not_affect_fitted_rate(self):
        changed = [dict(r) for r in self.rows]
        changed[-1]["label"] = 1
        a = historical_rate_experiment(self.rows, test_start="2026-10-01T00:00:00Z")
        b = historical_rate_experiment(changed, test_start="2026-10-01T00:00:00Z")
        self.assertEqual(a["fit_rate"], b["fit_rate"])

    def test_late_training_labels_excluded(self):
        late = case("late", "2026-08-01T00:00:00Z", 1,
                    available="2026-10-05T00:00:00Z")
        result = historical_rate_experiment(
            self.rows + [late], test_start="2026-10-01T00:00:00Z")
        self.assertEqual(result["train_n"], 2)

    def test_independent_label_provenance_required(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["label_source"] = ""
        with self.assertRaises(ValueError):
            historical_rate_experiment(rows, test_start="2026-10-01T00:00:00Z")

    def test_no_training_and_bad_smoothing_rejected(self):
        with self.assertRaises(ValueError):
            historical_rate_experiment(self.rows[-2:], test_start="2026-10-01T00:00:00Z")
        with self.assertRaises(ValueError):
            historical_rate_experiment(self.rows, test_start="2026-10-01T00:00:00Z",
                                       smoothing=float("nan"))


    def test_feature_evidence_enforced_when_provided(self):
        rows = [dict(r, features={"temp": {
            "value": 20, "observed_at": "2026-07-31T00:00:00Z",
            "available_at": "2026-07-31T01:00:00Z",
            "source_id": "fixture-weather"}}) for r in self.rows]
        result = historical_rate_experiment(
            rows, test_start="2026-10-01T00:00:00Z")
        self.assertEqual(result["feature_availability_audit"]["eligible"], 4)
        rows[0]["features"]["temp"]["available_at"] = "2026-10-12T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "as-of"):
            historical_rate_experiment(
                rows, test_start="2026-10-01T00:00:00Z")

    def test_partial_feature_evidence_rejected(self):
        rows = [dict(r) for r in self.rows]
        rows[0]["features"] = {"temp": {
            "value": 20, "observed_at": "2026-07-31T00:00:00Z",
            "available_at": "2026-07-31T00:00:00Z",
            "source_id": "fixture-weather"}}
        with self.assertRaisesRegex(ValueError, "Partial feature evidence"):
            historical_rate_experiment(
                rows, test_start="2026-10-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
