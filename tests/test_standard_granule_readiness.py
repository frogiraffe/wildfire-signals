import copy
import json
from pathlib import Path
import unittest

from fire_public.standard_granule_readiness import build_report


ROOT = Path(__file__).resolve().parents[1]


class StandardGranuleReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads((ROOT / 'docs/research/source-samples/antalya-standard-cmr-2025-01-06-07.json').read_text())
        cls.annual = json.loads((ROOT / 'public/data/antalya-annual-context-2023-2025.json').read_text())

    def test_real_catalog_pair_is_not_exposure_or_outcome(self):
        report = build_report(self.source, self.annual)
        self.assertEqual(report['population']['geolocation_granules'], 6)
        self.assertEqual(report['population']['active_fire_granules'], 6)
        self.assertEqual(report['population']['paired_intervals'], 6)
        self.assertEqual(report['population']['archived_noaa20_pixels'], 1)
        self.assertEqual(report['daily_rows'][0]['observation_state'], 'archived_candidate')
        self.assertEqual(report['daily_rows'][1]['observation_state'], 'no_archived_record_unverified_opportunity')
        self.assertIsNone(report['no_detection_count'])
        self.assertFalse(report['model_readiness']['scientific_comparison_eligible'])
        self.assertFalse(report['model_readiness']['operational_prediction_eligible'])
        self.assertTrue(all(not row['cell_observation_verified'] for row in report['daily_rows']))

    def test_tampered_or_incomplete_source_rejected(self):
        for mutate in [
            lambda x: x['queries'][0].update(body=x['queries'][0]['body'] + ' '),
            lambda x: x['queries'][0].update(cmr_hits=7),
            lambda x: x['queries'][1].update(url=x['queries'][1]['url'].replace('002', '2')),
        ]:
            source = copy.deepcopy(self.source)
            mutate(source)
            with self.assertRaises(ValueError):
                build_report(source, self.annual)

    def test_tampered_annual_evidence_rejected(self):
        annual = copy.deepcopy(self.annual)
        annual['candidate_provider_hours'].clear()
        with self.assertRaises(ValueError):
            build_report(self.source, annual)

    def test_replay_is_byte_identical(self):
        self.assertEqual(build_report(self.source, self.annual), build_report(self.source, self.annual))


if __name__ == '__main__':
    unittest.main()
