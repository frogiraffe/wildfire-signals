import unittest

from fire_public.observation_opportunity import classify_interval


class OpportunityStateTests(unittest.TestCase):
    def test_no_detection_requires_independent_acquisition_and_complete_retrieval(self):
        kwargs = {"archived_candidates":0,"retrieval":"complete"}
        self.assertEqual(classify_interval(**kwargs),
                         "no_archived_record_unverified_opportunity")
        with self.assertRaisesRegex(ValueError,"evidence hash"):
            classify_interval(**kwargs,acquisition="verified")
        self.assertEqual(classify_interval(**kwargs,acquisition="verified",
                         acquisition_evidence_sha256="a"*64),"no_reported_detection")
        self.assertEqual(classify_interval(**kwargs,acquisition="absent",
                         acquisition_evidence_sha256="a"*64),"no_confirmed_opportunity")
        with self.assertRaisesRegex(ValueError,"contradicts"):
            classify_interval(archived_candidates=1,retrieval="complete",acquisition="absent",
                              acquisition_evidence_sha256="a"*64)

    def test_failures_delays_and_archived_candidates_are_separate(self):
        self.assertEqual(classify_interval(archived_candidates=1,retrieval="complete"),
                         "archived_candidate")
        self.assertEqual(classify_interval(archived_candidates=0,retrieval="failed"),
                         "retrieval_failed")
        self.assertEqual(classify_interval(archived_candidates=0,retrieval="deferred"),
                         "retrieval_deferred")
        self.assertEqual(classify_interval(archived_candidates=0,retrieval="complete",
                         publication_delayed=True),"publication_delayed")
        self.assertEqual(classify_interval(archived_candidates=None,retrieval=None),"unknown")


if __name__ == "__main__": unittest.main()
