import copy
import hashlib
import json
from pathlib import Path
import unittest

from fire_public.static_sensitivity import build_sensitivity
from fire_public.historical_rollup import _bytes


ROOT = Path(__file__).resolve().parents[1]
RAW = Path('/tmp/ws-antalya-annual')


class PublishedStaticSensitivityTests(unittest.TestCase):
    def test_real_published_aggregate_is_internally_conserved(self):
        report = json.loads((ROOT / 'public/data/turkey-static-sensitivity-2023-2025.json').read_text())
        value = dict(report)
        digest = value.pop('evidence_sha256')
        self.assertEqual(hashlib.sha256(_bytes(value)).hexdigest(), digest)
        self.assertEqual(report['population']['country_source_rows'], 257907)
        self.assertEqual(report['population']['duplicate_source_rows'], 0)
        self.assertEqual(report['population']['selected_raw_pixels'], 1419)
        self.assertFalse(report['fire_rate_comparison_supported'])
        antalya = next(item for item in report['regions'] if item['region_id'] == 'ANTALYA_25KM')
        self.assertEqual(antalya['independently_excluded_raw_pixels'], 0)
        for year, all_pixels, unresolved in [(2023, 620, 490), (2024, 508, 347), (2025, 212, 50)]:
            rows = [row for row in antalya['year_sensor_rows'] if row['year'] == year]
            self.assertEqual(sum(row['all_raw_pixels'] for row in rows), all_pixels)
            self.assertEqual(sum(row['unresolved_recurrent_raw_pixels'] for row in rows), unresolved)
            self.assertEqual(sum(row['other_raw_pixels'] for row in rows), all_pixels - unresolved)


@unittest.skipUnless(RAW.is_dir(), 'real NASA country originals unavailable in this environment')
class StaticSensitivityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / 'examples/antalya-annual-manifest-2023-2025.json').read_text())
        cls.regions = json.loads((ROOT / 'examples/annual-spatial-regions-2023-2025.json').read_text())
        cls.spatial = json.loads((ROOT / 'public/data/turkey-spatial-recurrence-2023-2025.json').read_text())

    def test_real_pixel_sensitivity_preserves_unresolved_sources(self):
        report = build_sensitivity(self.manifest, self.regions, self.spatial, RAW)
        self.assertEqual(report['population']['selected_raw_pixels'], 1419)
        antalya = next(row for row in report['regions'] if row['region_id'] == 'ANTALYA_25KM')
        self.assertEqual(antalya['all_raw_pixels'], 1340)
        self.assertEqual(antalya['unresolved_recurrent_raw_pixels'], 887)
        self.assertEqual(antalya['independently_excluded_raw_pixels'], 0)
        self.assertEqual(sum(row['all_raw_pixels'] for row in antalya['year_sensor_rows']), 1340)
        self.assertTrue(all(row['all_raw_pixels'] == row['unresolved_recurrent_raw_pixels'] +
                            row['other_raw_pixels'] for row in antalya['year_sensor_rows']))
        self.assertFalse(report['fire_rate_comparison_supported'])

    def test_tampered_spatial_source_fails(self):
        spatial = copy.deepcopy(self.spatial)
        spatial['regions'][0]['selected_raw_pixels'] += 1
        with self.assertRaises(ValueError):
            build_sensitivity(self.manifest, self.regions, spatial, RAW)


if __name__ == '__main__':
    unittest.main()
