"""Synthetic chronology fixtures only; never real wildfire labels."""
import unittest
from fire_public.feature_availability_audit import audit_asof_features


def sample():
    return {"case_id": "c1", "decision_at": "2026-10-01T12:00:00Z",
            "features": {"temperature": {"value": 28.0,
                        "observed_at": "2026-10-01T10:00:00+00:00",
                        "available_at": "2026-10-01T11:00:00Z",
                        "source_id": "station-v1"}}}


class AsOfFeatureAuditTests(unittest.TestCase):
    def test_valid_chronology_still_does_not_authorize_training(self):
        result = audit_asof_features([sample()])
        self.assertEqual((result["eligible"], result["ineligible"]), (1, 0))
        self.assertFalse(result["model_training_authorized"])

    def test_future_availability_rejected(self):
        row = sample()
        row["features"]["temperature"]["available_at"] = "2026-10-02T00:00:00Z"
        self.assertIn("temperature:available_at_after_decision",
                      audit_asof_features([row])["cases"][0]["violations"])

    def test_future_observation_rejected(self):
        row = sample()
        row["features"]["temperature"]["observed_at"] = "2026-10-01T13:00:00Z"
        self.assertEqual(audit_asof_features([row])["eligible"], 0)

    def test_unknown_and_untraceable_fail_closed(self):
        row = sample()
        row["features"]["temperature"]["value"] = None
        row["features"]["temperature"]["source_id"] = ""
        self.assertEqual(audit_asof_features([row])["ineligible"], 1)

    def test_naive_timestamp_fails_closed(self):
        row = sample()
        row["features"]["temperature"]["available_at"] = "2026-10-01T11:00:00"
        self.assertEqual(audit_asof_features([row])["eligible"], 0)

    def test_equal_instants_with_offsets_allowed(self):
        row = sample()
        row["features"]["temperature"]["available_at"] = "2026-10-01T15:00:00+03:00"
        self.assertEqual(audit_asof_features([row])["eligible"], 1)

    def test_availability_cannot_precede_observation(self):
        row = sample()
        row["features"]["temperature"]["available_at"] = "2026-10-01T09:00:00Z"
        result = audit_asof_features([row])
        self.assertIn("temperature:available_before_observed",
                      result["cases"][0]["violations"])

    def test_empty_cohort_has_no_training_authority(self):
        result = audit_asof_features([])
        self.assertEqual(result["eligible"], 0)
        self.assertFalse(result["model_training_authorized"])

    def test_nonfinite_numeric_evidence_is_ineligible(self):
        for value in (float("nan"), float("inf"), float("-inf"), True):
            with self.subTest(value=repr(value)):
                row = sample()
                row["features"]["temperature"]["value"] = value
                self.assertEqual(audit_asof_features([row])["eligible"], 0)

    def test_future_source_issue_timestamp_is_ineligible(self):
        row = sample()
        row["features"]["temperature"]["issued_at"] = "2026-10-01T13:00:00Z"
        self.assertIn("temperature:issued_at_after_decision",
                      audit_asof_features([row])["cases"][0]["violations"])

    def test_earlier_source_issue_timestamp_is_accepted(self):
        row = sample()
        row["features"]["temperature"]["issued_at"] = "2026-10-01T11:00:00Z"
        self.assertEqual(audit_asof_features([row])["eligible"], 1)

    def test_duplicate_cases_rejected(self):
        with self.assertRaises(ValueError):
            audit_asof_features([sample(), sample()])

    def test_missing_features_rejected(self):
        row = sample()
        row["features"] = {}
        with self.assertRaises(ValueError):
            audit_asof_features([row])


if __name__ == "__main__":
    unittest.main()
