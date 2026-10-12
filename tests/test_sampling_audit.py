"""Sampling denominator and review attrition diagnostics, never prevalence."""
import json
import tempfile
import unittest
from pathlib import Path

from fire_public.sampling_audit import build_audit, render_html
from fire_public.label_review import _sha
from test_label_review import PROTOCOL, review


class SamplingAuditTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.queue=root/"queue.json"
        self.reviews=root/"reviews.json"
        self.protocol=root/"protocol.json"
        self.data={"schema_version":1,"state":"unadjudicated_review_queue",
            "as_of":"2026-10-13T00:00:00Z",
            "source_batches":[{"fire_year":2017,"batch_id":"batch-1",
                               "archived_polygon_count":1,"source_record_count":100}],
            "sampling_frame":{"name":"Independent <unsafe> frame",
                "source":"https://example.org/frame","input_sha256":"a"*64,
                "population_units":3,"sampled_units":2,
                "population_by_region":{"north":2,"south":1},
                "selected_by_region":{"north":1,"south":1},
                "selection_strategy":"seeded_hash_region_round_robin"},
            "cases":[
                {"case_id":"official:2017:1","kind":"retrospective_official_perimeter_review",
                 "source_fire_year":2017,"source_name":"<unsafe>","proposed_label":None},
                {"case_id":"frame:control-2017","kind":"independent_frame_review",
                 "sampling_unit_id":"control-2017","region_id":"north",
                 "decision_at":"2017-07-05T00:00:00Z","proposed_label":None},
                {"case_id":"frame:south-2017","kind":"independent_frame_review",
                 "sampling_unit_id":"south-2017","region_id":"south",
                 "decision_at":"2017-07-05T00:00:00Z","proposed_label":None},
            ]}
        self.queue.write_text(json.dumps(self.data),encoding="utf-8")
        self.protocol.write_text(json.dumps(PROTOCOL),encoding="utf-8")
        self.decisions=[review(self.data["cases"][0],0),
            {"case_id":"frame:control-2017","status":"unresolved",
             "reason":"Independent reviewers disagreed"},
            {"case_id":"frame:south-2017","status":"excluded",
             "reason":"Incomplete source coverage for this unit"}]
        self.save_reviews()

    def save_reviews(self):
        self.reviews.write_text(json.dumps({"schema_version":1,
            "queue_sha256":_sha(self.queue),"decisions":self.decisions}),encoding="utf-8")

    def test_queue_only_reports_source_and_frame_denominators(self):
        audit=build_audit(self.queue)
        self.assertEqual(audit["official_sources"][0]["published_source_ids"],100)
        self.assertEqual(audit["official_sources"][0]["archived_leads"],1)
        self.assertEqual(audit["frame_regions"][0]["selection_fraction"],0.5)
        self.assertIsNone(audit["review_attrition"])
        self.assertFalse(audit["population_prevalence_identifiable"])
        self.assertNotIn("prevalence",json.dumps(audit["frame_regions"]))

    def test_partial_review_attrition_keeps_unresolved_and_excluded(self):
        audit=build_audit(self.queue,self.reviews,self.protocol)
        self.assertEqual(audit["review_attrition"]["adjudicated_positive"],1)
        self.assertEqual(audit["review_attrition"]["unresolved"],1)
        self.assertEqual(audit["review_attrition"]["excluded"],1)
        self.assertEqual(audit["by_frame_region"]["north"]["unresolved"],1)
        self.assertEqual(audit["by_source_kind"]["independent_frame_review"]["excluded"],1)
        self.assertIn("&lt;unsafe&gt;",render_html(audit))
        self.assertNotIn("<unsafe>",render_html(audit))

    def test_tampered_frame_region_counts_are_rejected(self):
        self.data["sampling_frame"]["selected_by_region"]["north"]=2
        self.queue.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,"selected frame counts"):
            build_audit(self.queue)

    def test_review_must_cover_every_case(self):
        self.decisions.pop()
        self.save_reviews()
        with self.assertRaisesRegex(ValueError,"every queued case"):
            build_audit(self.queue,self.reviews,self.protocol)


if __name__=="__main__":
    unittest.main()
