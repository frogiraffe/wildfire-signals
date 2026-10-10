import unittest
import gzip
import json
import io
import os
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fire_public.cli import main, previous_snapshot, verify_free


class FreePlanTests(unittest.TestCase):
    def test_recent_snapshot_skips_provider_reads_and_publication(self):
        prior = {"manifest":{"schema_version":1,
                             "last_scan_at":(datetime.now(timezone.utc) -
                                             timedelta(minutes=54)).isoformat()}}
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot"}
        with patch.dict(os.environ, env, clear=True), \
                patch("fire_public.cli.verify_free"), \
                patch("fire_public.cli.previous_snapshot", return_value=prior), \
                patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                patch("fire_public.cli.fetch_nifc", return_value=[]) as nifc, \
                patch("fire_public.cli.fetch_cwfis", return_value=[]) as cwfis, \
                patch("fire_public.cli.current_key", return_value=None), \
                patch("fire_public.cli.publish", return_value="snapshot:test") as publish, \
                redirect_stdout(io.StringIO()):
            main()
        firms.assert_not_called()
        nifc.assert_not_called()
        cwfis.assert_not_called()
        publish.assert_not_called()

    def test_manual_force_collects_even_when_snapshot_is_recent(self):
        prior = {"manifest":{"schema_version":1,
                             "last_scan_at":datetime.now(timezone.utc).isoformat()}}
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot",
               "FORCE_COLLECTION":"true"}
        with patch.dict(os.environ, env, clear=True), \
                patch("fire_public.cli.verify_free"), \
                patch("fire_public.cli.previous_snapshot", return_value=prior), \
                patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                patch("fire_public.cli.fetch_nifc", return_value=[]), \
                patch("fire_public.cli.fetch_cwfis", return_value=[]), \
                patch("fire_public.cli.current_key", return_value=None), \
                patch("fire_public.cli.publish", return_value="snapshot:test") as publish, \
                redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(firms.call_count, 2)
        publish.assert_called_once()

    def test_invalid_prior_timestamp_does_not_suppress_collection(self):
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot"}
        for prior in [None,
                      {"manifest":{"schema_version":1}},
                      {"manifest":{"schema_version":1,"last_scan_at":"bad-date"}},
                      {"manifest":{"schema_version":1,"last_scan_at":datetime.now().isoformat()}},
                      {"manifest":{"schema_version":1,"last_scan_at":(
                          datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}}]:
            with self.subTest(prior=prior), patch.dict(os.environ, env, clear=True), \
                    patch("fire_public.cli.verify_free"), \
                    patch("fire_public.cli.previous_snapshot", return_value=prior), \
                    patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                    patch("fire_public.cli.fetch_nifc", return_value=[]), \
                    patch("fire_public.cli.fetch_cwfis", return_value=[]), \
                    patch("fire_public.cli.current_key", return_value=None), \
                    patch("fire_public.cli.publish", return_value="snapshot:test"), \
                    redirect_stdout(io.StringIO()):
                main()
                self.assertEqual(firms.call_count, 2)

    def test_fifty_five_minute_old_snapshot_allows_collection(self):
        prior = {"manifest":{"schema_version":1,
                             "last_scan_at":(datetime.now(timezone.utc) -
                                             timedelta(minutes=55)).isoformat()}}
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot"}
        with patch.dict(os.environ, env, clear=True), \
                patch("fire_public.cli.verify_free"), \
                patch("fire_public.cli.previous_snapshot", return_value=prior), \
                patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                patch("fire_public.cli.fetch_nifc", return_value=[]), \
                patch("fire_public.cli.fetch_cwfis", return_value=[]), \
                patch("fire_public.cli.current_key", return_value=None), \
                patch("fire_public.cli.publish", return_value="snapshot:test"), \
                redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(firms.call_count, 2)

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

    @patch("fire_public.cli.urlopen")
    def test_previous_snapshot_requests_gzip_to_preserve_large_history(self, urlopen):
        snapshot = {"manifest":{"schema_version":1}, "events":[{"event_id":"prior"}],
                    "padding":"x" * (5 * 1024 * 1024)}
        plain = json.dumps(snapshot).encode()
        compressed = gzip.compress(plain)

        class Response:
            status = 200
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self, size): return self.body[:size]

        def serve(request, timeout):
            accepted = request.get_header("Accept-encoding")
            return Response(compressed if accepted == "gzip" else plain)

        urlopen.side_effect = serve
        result = previous_snapshot("https://map.pages.dev/api/snapshot")
        self.assertIsNotNone(result)
        self.assertEqual(result["events"][0]["event_id"], "prior")


if __name__ == "__main__":
    unittest.main()
