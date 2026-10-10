import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from fire_public.worker_setup import ensure_workers_subdomain


ACCOUNT = "a" * 32


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def response(result, success=True):
    return Response(json.dumps({"success": success, "result": result}).encode())


class WorkerSetupTests(unittest.TestCase):
    @patch("fire_public.worker_setup.urlopen")
    def test_existing_subdomain_is_preserved(self, open_url):
        open_url.return_value = response({"subdomain": "existing-name"})
        self.assertEqual(ensure_workers_subdomain(ACCOUNT, "secret"), "existing-name")
        self.assertEqual(open_url.call_count, 1)
        self.assertEqual(open_url.call_args.args[0].get_method(), "GET")

    @patch("fire_public.worker_setup.urlopen")
    def test_missing_subdomain_is_created_once(self, open_url):
        name = f"wildfire-signals-{ACCOUNT}"
        missing = HTTPError("https://example.test", 404, "missing", {}, None)
        open_url.side_effect = [missing, response({"subdomain": name})]
        self.assertEqual(ensure_workers_subdomain(ACCOUNT, "secret"), name)
        request = open_url.call_args.args[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(json.loads(request.data), {"subdomain": name})

    @patch("fire_public.worker_setup.urlopen")
    def test_forbidden_does_not_attempt_creation(self, open_url):
        open_url.side_effect = HTTPError("https://example.test", 403, "forbidden", {}, None)
        with self.assertRaises(HTTPError):
            ensure_workers_subdomain(ACCOUNT, "secret")
        self.assertEqual(open_url.call_count, 1)

    @patch("fire_public.worker_setup.urlopen")
    def test_malformed_create_response_fails(self, open_url):
        missing = HTTPError("https://example.test", 404, "missing", {}, None)
        open_url.side_effect = [missing, response({"subdomain": "wrong"})]
        with self.assertRaises(RuntimeError):
            ensure_workers_subdomain(ACCOUNT, "secret")


if __name__ == "__main__":
    unittest.main()
