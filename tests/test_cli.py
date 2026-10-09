import unittest
from unittest.mock import patch

from fire_public.cli import verify_free


class FreePlanTests(unittest.TestCase):
    @patch("fire_public.cli.api_request")
    def test_paid_plan_refused(self, request):
        request.return_value = {"result_info":{"total_pages":1},
            "result": [{"state": "Paid", "rate_plan": {"id": "pro"}, "price": 5}]}
        with self.assertRaises(RuntimeError):
            verify_free("a" * 32, "token")

    @patch("fire_public.cli.api_request")
    def test_free_plan_accepted(self, request):
        request.return_value = {"result_info":{"total_pages":1},
            "result": [{"state": "Provisioned", "rate_plan": {"id": "free"}, "price": 0}]}
        verify_free("a" * 32, "token")

    @patch("fire_public.cli.api_request")
    def test_second_subscription_page_refused(self, request):
        request.return_value = {"result_info":{"total_pages":2},
            "result": [{"state": "Provisioned", "rate_plan": {"id": "free"}, "price": 0}]}
        with self.assertRaises(RuntimeError):
            verify_free("a" * 32, "token")


if __name__ == "__main__":
    unittest.main()
