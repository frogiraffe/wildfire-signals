"""Offline workbench regression tests. All observations are synthetic."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fire_public.holdout_workbench import load_jsonl, run_report, html_report


def item(index, region, split, label, year):
    decision = f"{year}-01-0{index % 2 + 1}T00:00:00Z"
    return {
        "case_sampling_id": "unit-" + str(index),
        "event_id": "event-" + str(index),
        "region_id": region,
        "decision_at": decision,
        "feature_latest_available_at": decision,
        "feature_cutoff_at": decision,
        "label_available_at": f"{year}-02-01T00:00:00Z",
        "label_verified_at": f"{year}-02-02T00:00:00Z",
        "label": label,
        "split": split,
        "label_source": "independent-review",
        "label_source_id": str(index),
        "label_evidence_url": "https://example.org/evidence/" + str(index),
    }


def fixtures():
    return [
        item(0, "north", "train", 0, 2023),
        item(1, "north", "train", 1, 2023),
        item(2, "south", "test", 0, 2025),
        item(3, "south", "test", 1, 2025),
    ]


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cohort = self.root / "cohort.jsonl"
        self.manifest = self.root / "manifest.json"
        self.manifest.write_text(json.dumps({"target_name": "test-target",
                                             "horizon_hours": 24,
                                             "study_region": "test-region"}))
        self.write_rows(fixtures())

    def write_rows(self, rows):
        self.cohort.write_text("".join(json.dumps(row) + "\n" for row in rows))

    def run_checked(self, **kwargs):
        with patch("fire_public.holdout_workbench._manifest"), patch(
            "fire_public.holdout_workbench._audit_rows", return_value={"n": 4}):
            return run_report(self.cohort, self.manifest, **kwargs)

    def test_deterministic_aggregate_and_digest(self):
        first = self.run_checked()
        second = self.run_checked()
        self.assertEqual(first, second)
        self.assertTrue(first["eligible_for_model_evaluation"])
        self.assertEqual(first["source"]["cohort_sha256"],
                         hashlib.sha256(self.cohort.read_bytes()).hexdigest())
        self.assertIsNone(first["measured_model_skill"])
        self.assertFalse(first["independently_verified_ground_truth"])
        self.assertNotIn("case_sampling_id", json.dumps(first))

    def test_event_contamination_is_blocked(self):
        rows = fixtures()
        rows[2]["event_id"] = rows[0]["event_id"]
        self.write_rows(rows)
        self.assertIn("event_overlap", self.run_checked()["holdout"]["failed_gates"])

    def test_region_contamination_is_blocked(self):
        rows = fixtures()
        rows[2]["region_id"] = "north"
        self.write_rows(rows)
        self.assertIn("region_overlap", self.run_checked()["holdout"]["failed_gates"])

    def test_future_feature_availability_is_blocked(self):
        rows = fixtures()
        rows[2]["feature_latest_available_at"] = "2026-01-01T00:00:00Z"
        self.write_rows(rows)
        self.assertIn("future_feature_leakage", self.run_checked()["holdout"]["failed_gates"])

    def test_missing_feature_availability_fails_closed(self):
        rows = fixtures()
        del rows[2]["feature_latest_available_at"]
        self.write_rows(rows)
        with self.assertRaises(ValueError):
            self.run_checked()

    def test_html_escapes_user_content(self):
        result = self.run_checked()
        result["source"]["target_name"] = "<script>alert(1)</script>"
        body = html_report(result)
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("<script>", body)
        self.assertIn("Content-Security-Policy", body)

    def test_jsonl_rejects_non_object(self):
        self.cohort.write_text('["not", "a", "row"]\n')
        with self.assertRaises(ValueError):
            load_jsonl(self.cohort)

    def test_jsonl_rejects_oversized_row(self):
        self.cohort.write_text('{"x":"' + "a" * 35000 + '"}\n')
        with self.assertRaises(ValueError):
            load_jsonl(self.cohort)

    def test_jsonl_rejects_symlink(self):
        link = self.root / "alias"
        link.symlink_to(self.cohort)
        with self.assertRaises(ValueError):
            load_jsonl(link)

    def test_no_validated_skill_claim_even_with_clean_split(self):
        result = self.run_checked()
        self.assertEqual(result["scientific_tier"], "experimental")
        self.assertEqual(result["report_type"], "holdout_eligibility_not_prediction_skill")


if __name__ == "__main__":
    unittest.main()
