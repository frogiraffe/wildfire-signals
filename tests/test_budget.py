import unittest

from fire_public.publish import MAX_VALUE_BYTES, TTL_SECONDS
from fire_public.cli import MIN_SCAN_INTERVAL


class BudgetTests(unittest.TestCase):
    def test_hourly_versions_fit_kv_free_storage(self):
        # Even if every fallback publishes at the minimum allowed interval.
        interval = int(MIN_SCAN_INTERVAL.total_seconds())
        retained_versions = (TTL_SECONDS + interval - 1) // interval + 1
        self.assertLess(retained_versions * MAX_VALUE_BYTES, 1_000_000_000)
        self.assertLess(((24 * 3600 + interval - 1) // interval) * 2, 1000)


if __name__ == '__main__':
    unittest.main()
