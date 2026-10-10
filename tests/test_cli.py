import unittest
import gzip
import json
from unittest.mock import patch

from fire_public.cli import previous_snapshot, verify_free


class FreePlanTests(unittest.TestCase):
    @patch("fire_public.cli.api_request")
    def test_paid_plan_refused(self, request):
        request.return_value = {"result_info":{"count":1,"page":1,"per_page":20,"total_count":1},
            "result": [{"state": "Paid", "rate_plan": {"id": "pro"}, "price": 5}]}
        with self.assertRaises(RuntimeError):
            verify_free("a" * 32, "token")

    @patch("fire_public.cli.api_request")
    def test_free_plan_accepted(self, request):
        request.return_value = {"result_info":{"count":1,"page":1,"per_page":20,"total_count":1},
            "result": [{"state": "Provisioned", "rate_plan": {"id": "free"}, "price": 0}]}
        verify_free("a" * 32, "token")

    @patch("fire_public.cli.api_request")
    def test_free_plan_accepted_with_cursor_pagination(self, request):
        request.return_value = {"result_info": {"page": 1, "per_page": 25, "next_page": None},
            "result": [{"state": "Provisioned", "rate_plan": {"id": "free"}, "price": 0}]}
        verify_free("a" * 32, "token")

    @patch("fire_public.cli.api_request")
    def test_second_subscription_page_refused(self, request):
        request.return_value = {"result_info":{"count":1,"page":1,"per_page":20,"total_count":21},
            "result": [{"state": "Provisioned", "rate_plan": {"id": "free"}, "price": 0}]}
        with self.assertRaises(RuntimeError):
            verify_free("a" * 32, "token")

    @patch("fire_public.cli.api_request")
    def test_cursor_next_page_refused(self, request):
        request.return_value = {"result_info": {"page": 1, "per_page": 25, "next_page": 2},
            "result": [{"state": "Provisioned", "rate_plan": {"id": "free"}, "price": 0}]}
        with self.assertRaisesRegex(RuntimeError, "cannot verify every"):
            verify_free("a" * 32, "token")

    @patch("fire_public.cli.api_request")
    def test_empty_cursor_page_refused(self, request):
        request.return_value = {"result_info": {"page": 1, "per_page": 25, "next_page": None},
            "result": []}
        with self.assertRaisesRegex(RuntimeError, "subscription could not be verified"):
            verify_free("a" * 32, "token")

    @patch("fire_public.cli.api_request")
    def test_false_cursor_marks_last_page(self, request):
        request.return_value = {"result_info": {"page": 1, "per_page": 25, "next_page": False},
            "result": [{"state": "Provisioned", "rate_plan": {"id": "free"}, "price": 0}]}
        verify_free("a" * 32, "token")

    @patch("fire_public.cli.api_request")
    def test_empty_page_requires_matching_dashboard_attestation(self, request):
        request.return_value = {"result_info": {"page": 1, "per_page": 25, "next_page": False},
            "result": []}
        with self.assertRaisesRegex(RuntimeError, "subscription could not be verified"):
            verify_free("a" * 32, "token")
        verify_free("a" * 32, "token", attested_account="a" * 32)
        with self.assertRaisesRegex(RuntimeError, "subscription could not be verified"):
            verify_free("a" * 32, "token", attested_account="b" * 32)

    @patch("fire_public.cli.urlopen")
    def test_compressed_public_snapshot_readback(self, urlopen):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self, size):
                return gzip.compress(json.dumps({"manifest":{"schema_version":1},
                    "events":[{"event_id":"prior"}]}).encode())[:size]
        urlopen.return_value = Response()
        self.assertEqual(previous_snapshot("https://map.pages.dev/api/snapshot")
                         ["events"][0]["event_id"], "prior")


if __name__ == "__main__":
    unittest.main()
