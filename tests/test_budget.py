import unittest

from fire_public.publish import MAX_VALUE_BYTES, TTL_SECONDS


class BudgetTests(unittest.TestCase):
    def test_hourly_versions_fit_kv_free_storage(self):
        # Two writes/hour and at most 26 retained 20-MiB values; pointer is tiny.
        retained_versions = (TTL_SECONDS + 3599) // 3600 + 1
        self.assertLess(retained_versions * MAX_VALUE_BYTES, 1024 ** 3)
        self.assertLess(24 * 2, 1000)


if __name__ == '__main__':
    unittest.main()
