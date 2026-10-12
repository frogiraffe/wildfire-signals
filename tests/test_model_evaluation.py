"""Regression tests for probability evaluation; examples are synthetic fixtures."""
import unittest
from fire_public.model_evaluation import evaluate_binary


def row(event_id, label, prediction, baseline=0.5):
    return {"event_id": event_id, "region_id": "fixture-region",
            "decision_at": "2026-10-10T12:00:00Z",
            "label_available_at": "2026-10-11T12:00:00Z",
            "split": "test", "label": label, "prediction": prediction,
            "baseline_prediction": baseline}


class EvaluationTests(unittest.TestCase):
    def test_perfect_forecasts_beat_baseline(self):
        result = evaluate_binary([row("a", 1, 1.0), row("b", 0, 0.0)])
        self.assertEqual(result["brier_score"], 0)
        self.assertEqual(result["baseline_brier_score"], 0.25)
        self.assertEqual(result["brier_skill_score"], 1)
        self.assertEqual(result["positives"], 1)

    def test_constant_forecasts_match_baseline(self):
        result = evaluate_binary([row("a", 1, 0.5), row("b", 0, 0.5)])
        self.assertEqual(result["brier_skill_score"], 0)

    def test_no_claim_if_baseline_perfect(self):
        result = evaluate_binary([row("a", 1, 1, 1)])
        self.assertIsNone(result["brier_skill_score"])

    def test_bad_probabilities_and_labels_rejected(self):
        for key, value in (("prediction", -0.1), ("prediction", float("nan")),
                           ("prediction", 1.2), ("label", True),
                           ("split", "train")):
            with self.subTest(key=key, value=value):
                record = row("a", 1, 0.6)
                record[key] = value
                with self.assertRaises(ValueError):
                    evaluate_binary([record])

    def test_duplicate_or_early_label_rejected(self):
        r = row("a", 0, 0.2)
        with self.assertRaises(ValueError):
            evaluate_binary([r, r])
        r["label_available_at"] = "2026-10-10T11:59:00Z"
        with self.assertRaises(ValueError):
            evaluate_binary([r])

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_binary([])


if __name__ == "__main__":
    unittest.main()
