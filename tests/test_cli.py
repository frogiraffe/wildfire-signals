import unittest
import gzip
import json
import io
import os
from pathlib import Path
from urllib.error import HTTPError
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fire_public.cli import current_pointer, main, previous_snapshot, verify_free


class FreePlanTests(unittest.TestCase):
    def test_enabled_pixel_scan_receipt_is_written_after_publication(self):
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot",
               "ANALYSIS_RECEIPT_DIR":"/tmp/wildfire-test-receipts",
               "ENABLE_ANALYSIS_ARCHIVE":"true"}
        with patch.dict(os.environ,env,clear=True), \
                patch('fire_public.cli.should_archive_analysis',return_value=True), \
                patch('fire_public.cli.verify_free'), \
                patch('fire_public.cli.previous_snapshot',return_value=None), \
                patch('fire_public.cli.current_pointer',return_value=None), \
                patch('fire_public.cli.fetch_firms_with_archive',return_value=[]), \
                patch('fire_public.cli.fetch_nifc',return_value=[]), \
                patch('fire_public.cli.fetch_cwfis',return_value=[]), \
                patch('fire_public.cli.publish',return_value='snapshot:'+'a'*64), \
                patch('fire_public.cli.write_scan_receipt',return_value=Path('receipt.json.gz')) as receipt, \
                patch('fire_public.cli.maybe_write_analysis_receipt',return_value={}), \
                redirect_stdout(io.StringIO()):
            main()
        receipt.assert_called_once()

    def test_pointer_read_failure_aborts_before_provider_requests_or_publication(self):
        prior = {"manifest":{"schema_version":1,
                             "last_scan_at":(datetime.now(timezone.utc) -
                                             timedelta(hours=2)).isoformat()}}
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot"}
        with patch.dict(os.environ, env, clear=True), \
                patch("fire_public.cli.verify_free"), \
                patch("fire_public.cli.previous_snapshot", return_value=prior), \
                patch("fire_public.cli.current_pointer", side_effect=OSError("KV unavailable")), \
                patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                patch("fire_public.cli.fetch_nifc", return_value=[]), \
                patch("fire_public.cli.fetch_cwfis", return_value=[]), \
                patch("fire_public.cli.publish", return_value="snapshot:test") as publish:
            with self.assertRaisesRegex(OSError, "KV unavailable"):
                main()
        firms.assert_not_called()
        publish.assert_not_called()

    def test_newer_pointer_prevents_duplicate_when_public_snapshot_is_cached(self):
        prior = {"manifest":{"schema_version":1,
                             "last_scan_at":(datetime.now(timezone.utc) -
                                             timedelta(hours=2)).isoformat()}}
        pointer = {"key":"snapshot:" + "a" * 64,
                   "last_scan_at":datetime.now(timezone.utc).isoformat()}
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot"}
        with patch.dict(os.environ, env, clear=True), \
                patch("fire_public.cli.verify_free"), \
                patch("fire_public.cli.previous_snapshot", return_value=prior), \
                patch("fire_public.cli.current_pointer", return_value=pointer), \
                patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                patch("fire_public.cli.fetch_nifc", return_value=[]), \
                patch("fire_public.cli.fetch_cwfis", return_value=[]), \
                patch("fire_public.cli.publish", return_value="snapshot:test") as publish, \
                redirect_stdout(io.StringIO()) as output:
            main()
        self.assertEqual(json.loads(output.getvalue())["skipped"], "recent_snapshot")
        firms.assert_not_called()
        publish.assert_not_called()

    @patch("fire_public.cli.urlopen")
    def test_pointer_distinguishes_empty_namespace_from_read_failure(self, urlopen):
        missing = HTTPError("https://example.test/current", 404, "missing", {}, io.BytesIO())
        unavailable = HTTPError("https://example.test/current", 503, "unavailable", {}, io.BytesIO())
        try:
            urlopen.side_effect = missing
            with patch("fire_public.cli.api_request", return_value={
                    "success":True, "result":{"id":"b" * 32}}) as request:
                self.assertIsNone(current_pointer("a" * 32, "b" * 32, "token"))
            request.assert_called_once()
            with patch("fire_public.cli.api_request", return_value={
                    "success":True, "result":{"id":"c" * 32}}):
                with self.assertRaisesRegex(RuntimeError, "namespace"):
                    current_pointer("a" * 32, "b" * 32, "token")
            namespace_missing = HTTPError("https://example.test/namespace", 404,
                                          "missing", {}, io.BytesIO())
            try:
                with patch("fire_public.cli.api_request", side_effect=namespace_missing):
                    with self.assertRaises(HTTPError):
                        current_pointer("a" * 32, "b" * 32, "token")
            finally:
                namespace_missing.close()
            urlopen.side_effect = unavailable
            with self.assertRaises(HTTPError):
                current_pointer("a" * 32, "b" * 32, "token")
        finally:
            missing.close()
            unavailable.close()

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
                patch("fire_public.cli.current_pointer", return_value=None), \
                patch("fire_public.cli.publish", return_value="snapshot:test") as publish, \
                redirect_stdout(io.StringIO()):
            main()
        firms.assert_not_called()
        nifc.assert_not_called()
        cwfis.assert_not_called()
        publish.assert_not_called()

    def test_manual_force_collects_with_recent_or_unreadable_snapshot(self):
        recent = {"manifest":{"schema_version":1,
                              "last_scan_at":datetime.now(timezone.utc).isoformat()}}
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot",
               "FORCE_COLLECTION":"true"}
        for prior in (recent, None):
            with self.subTest(prior=prior), patch.dict(os.environ, env, clear=True), \
                    patch("fire_public.cli.verify_free"), \
                    patch("fire_public.cli.previous_snapshot", return_value=prior), \
                    patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                    patch("fire_public.cli.fetch_nifc", return_value=[]), \
                    patch("fire_public.cli.fetch_cwfis", return_value=[]), \
                    patch("fire_public.cli.current_pointer", return_value=None), \
                    patch("fire_public.cli.publish", return_value="snapshot:test") as publish, \
                    redirect_stdout(io.StringIO()):
                main()
            self.assertEqual(firms.call_count, 2)
            publish.assert_called_once()

    def test_malformed_public_history_uses_recent_verified_pointer_without_collection(self):
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot"}
        for prior in [{"manifest":{"schema_version":1}},
                      {"manifest":{"schema_version":1,"last_scan_at":"bad-date"}},
                      {"manifest":{"schema_version":1,"last_scan_at":datetime.now().isoformat()}}]:
            with self.subTest(prior=prior), patch.dict(os.environ, env, clear=True), \
                    patch("fire_public.cli.verify_free"), \
                    patch("fire_public.cli.previous_snapshot", return_value=prior), \
                    patch("fire_public.cli.current_pointer", return_value={
                        "key":"snapshot:" + "a" * 64,
                        "last_scan_at":datetime.now(timezone.utc).isoformat()}), \
                    patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                    patch("fire_public.cli.fetch_nifc", return_value=[]) as nifc, \
                    patch("fire_public.cli.fetch_cwfis", return_value=[]) as cwfis, \
                    patch("fire_public.cli.publish", return_value="snapshot:test") as publish, \
                    redirect_stdout(io.StringIO()) as output:
                main()
                self.assertEqual(json.loads(output.getvalue())["skipped"], "recent_snapshot")
                firms.assert_not_called()
                nifc.assert_not_called()
                cwfis.assert_not_called()
                publish.assert_not_called()

    def test_malformed_public_history_is_excluded_from_recovery_snapshot(self):
        prior = {"manifest":{"schema_version":1,"last_scan_at":"bad-date"},
                 "events":[{"event_id":"bad","observed_at":"also-bad"}]}
        pointer = {"key":"snapshot:" + "a" * 64,
                   "last_scan_at":(datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot"}
        with patch.dict(os.environ, env, clear=True), \
                patch("fire_public.cli.verify_free"), \
                patch("fire_public.cli.previous_snapshot", return_value=prior), \
                patch("fire_public.cli.current_pointer", return_value=pointer), \
                patch("fire_public.cli.fetch_firms", return_value=[]), \
                patch("fire_public.cli.fetch_nifc", return_value=[]), \
                patch("fire_public.cli.fetch_cwfis", return_value=[]), \
                patch("fire_public.cli.build_snapshot", return_value={
                    "events":[], "incidents":[]}) as build, \
                patch("fire_public.cli.publish", return_value="snapshot:test"), \
                redirect_stdout(io.StringIO()):
            main()
        self.assertIsNone(build.call_args.kwargs["previous"])

    def test_malformed_pointer_timestamp_aborts_even_when_pages_is_valid(self):
        prior = {"manifest":{"schema_version":1,
                             "last_scan_at":(datetime.now(timezone.utc) -
                                             timedelta(hours=2)).isoformat()}}
        pointer = {"key":"snapshot:" + "a" * 64,"last_scan_at":"bad-date"}
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot",
               "FORCE_COLLECTION":"true"}
        with patch.dict(os.environ, env, clear=True), \
                patch("fire_public.cli.verify_free"), \
                patch("fire_public.cli.previous_snapshot", return_value=prior), \
                patch("fire_public.cli.current_pointer", return_value=pointer), \
                patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                patch("fire_public.cli.publish") as publish:
            with self.assertRaisesRegex(RuntimeError, "pointer timestamp"):
                main()
        firms.assert_not_called()
        publish.assert_not_called()

    def test_missing_public_snapshot_uses_pointer_cadence_and_recovers(self):
        env = {"CLOUDFLARE_ACCOUNT_ID":"a" * 32,
               "CLOUDFLARE_KV_NAMESPACE_ID":"b" * 32,
               "CLOUDFLARE_API_TOKEN":"test-token", "FIRMS_MAP_KEY":"test-key",
               "PUBLIC_SNAPSHOT_URL":"https://wildfire-signals.pages.dev/api/snapshot"}
        old = {"key":"snapshot:" + "a" * 64,
               "last_scan_at":(datetime.now(timezone.utc) - timedelta(days=8)).isoformat()}
        recent = {"key":"snapshot:" + "a" * 64,
                  "last_scan_at":datetime.now(timezone.utc).isoformat()}
        for pointer, expected_reads in [(None, 2), (old, 2), (recent, 0),
                                        ({"key":"snapshot:" + "a" * 64}, 0)]:
            with self.subTest(pointer=pointer), patch.dict(os.environ, env, clear=True), \
                    patch("fire_public.cli.verify_free"), \
                    patch("fire_public.cli.previous_snapshot", return_value=None), \
                    patch("fire_public.cli.current_pointer", return_value=pointer), \
                    patch("fire_public.cli.fetch_firms", return_value=[]) as firms, \
                    patch("fire_public.cli.fetch_nifc", return_value=[]), \
                    patch("fire_public.cli.fetch_cwfis", return_value=[]), \
                    patch("fire_public.cli.publish", return_value="snapshot:test") as publish, \
                    redirect_stdout(io.StringIO()):
                main()
            self.assertEqual(firms.call_count, expected_reads)
            self.assertEqual(publish.call_count, int(expected_reads > 0))

    def test_fifty_five_minute_old_snapshot_allows_collection(self):
        prior = {"manifest":{"schema_version":1,
                             "last_scan_at":(datetime.now(timezone.utc) -
                                             timedelta(minutes=55)).isoformat()}}
        pointer = {"key":"snapshot:" + "a" * 64,
                   "last_scan_at":prior["manifest"]["last_scan_at"]}
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
                patch("fire_public.cli.current_pointer", return_value=pointer), \
                patch("fire_public.cli.publish", return_value="snapshot:test") as publish, \
                redirect_stdout(io.StringIO()):
            main()
        self.assertEqual(firms.call_count, 2)
        self.assertEqual(publish.call_args.kwargs["previous_key"], pointer["key"])

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
