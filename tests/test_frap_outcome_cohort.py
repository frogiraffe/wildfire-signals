import json
from pathlib import Path
import unittest

from fire_public.frap_outcome_cohort import build_cohort


ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / 'docs/research/source-samples'


class FrapOutcomeCohortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geo = (SAMPLES / 'sacramento-frap-2023-2025.geojson').read_bytes()
        cls.meta = (SAMPLES / 'sacramento-frap-layer-metadata.json').read_bytes()
        cls.count = (SAMPLES / 'sacramento-frap-count-2023-2025.json').read_bytes()

    def test_real_official_perimeters_are_positive_evidence_not_negatives(self):
        report = build_cohort(self.geo, self.meta, self.count)
        self.assertEqual(report['population']['source_perimeters'], 9)
        self.assertEqual(report['population']['ground_or_air_suppression_evidence'], 5)
        self.assertEqual(report['population']['other_method_or_objective_unknown'], 4)
        self.assertEqual(report['population']['verified_negative_outcomes'], 0)
        self.assertFalse(report['occurrence_model_eligible'])
        self.assertTrue(all(row['geometry_is_ignition_point'] is False for row in report['cases']))
        self.assertTrue(all(row['decision_time_available'] is False for row in report['cases']))
        self.assertTrue(all(row['event_ascertainment_independence_verified'] is False
                            for row in report['cases']))
        self.assertEqual({row['source_year'] for row in report['cases']}, {2023, 2024, 2025})
        self.assertTrue(all(row['source_alarm_date_calendar'].startswith(str(row['source_year']))
                            for row in report['cases']))
        self.assertTrue(all(row['geometry_bounds_wgs84'][0] <= -121.31 and
                            row['geometry_bounds_wgs84'][2] >= -121.88 for row in report['cases']))

    def test_source_hash_geometry_and_code_contract_fail_closed(self):
        with self.assertRaises(ValueError):
            build_cohort(self.geo + b' ', self.meta, self.count)
        with self.assertRaises(ValueError):
            build_cohort(self.geo, self.meta + b' ', self.count)
        with self.assertRaises(ValueError):
            build_cohort(self.geo, self.meta, b'{"count":8}')
        geo = json.loads(self.geo)
        geo['features'][0]['geometry']['coordinates'][0][0][0] = 300
        geo['features'][0]['geometry']['coordinates'][0][-1][0] = 300
        with self.assertRaises(ValueError):
            build_cohort(json.dumps(geo).encode(), self.meta, self.count, verify_source_hashes=False)
        geo = json.loads(self.geo)
        geo['features'][0]['geometry']['coordinates'][0][-1][0] += 0.1
        with self.assertRaisesRegex(ValueError, 'ring not closed'):
            build_cohort(json.dumps(geo).encode(), self.meta, self.count, verify_source_hashes=False)

    def test_replay_deterministic(self):
        self.assertEqual(build_cohort(self.geo, self.meta, self.count),
                         build_cohort(self.geo, self.meta, self.count))


if __name__ == '__main__':
    unittest.main()
