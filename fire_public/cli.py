"""Hourly collector; refuses to write before a Free subscription check."""
import json
import gzip
import io
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from .collect import FIRMS_SOURCES, build_snapshot, fetch_cwfis, fetch_firms, fetch_nifc
from .publish import publish

API = "https://api.cloudflare.com/client/v4"
HEX_ID = re.compile(r"^[a-f0-9]{32}$")


def api_request(url, token, *, data=None):
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/octet-stream"
    with urlopen(Request(url, data=data, headers=headers,
                         method="PUT" if data is not None else "GET"), timeout=30) as response:
        payload = json.load(response)
    if payload.get("success") is not True:
        raise RuntimeError("Cloudflare API request failed")
    return payload


def verify_free(account, token):
    payload = api_request(f"{API}/accounts/{account}/subscriptions", token)
    result = payload.get("result")
    info = payload.get("result_info") or {}
    page, per_page = info.get("page"), info.get("per_page")
    valid_number = lambda value: isinstance(value, int) and not isinstance(value, bool)
    if (not valid_number(page) or not valid_number(per_page)
            or page != 1 or per_page < 1):
        raise RuntimeError("cannot verify every Cloudflare subscription page")
    if "next_page" in info and "count" not in info and "total_count" not in info:
        complete = info["next_page"] is None
    else:
        count, total_count = info.get("count"), info.get("total_count")
        complete = (valid_number(count) and valid_number(total_count)
                    and count == total_count and total_count <= per_page)
    if not complete:
        raise RuntimeError("cannot verify every Cloudflare subscription page")
    if not isinstance(result, list) or not result:
        raise RuntimeError("Cloudflare subscription could not be verified")
    if "count" in info and len(result) != info["count"]:
        raise RuntimeError("Cloudflare subscription count mismatch")
    for item in result:
        if (item.get("state") != "Provisioned" or
                (item.get("rate_plan") or {}).get("id") not in {"free", "partners_free"}
                or item.get("price") != 0):
            raise RuntimeError("paid or unknown Cloudflare subscription; refusing publication")


def previous_snapshot(url):
    if not url:
        return None
    if not url.startswith("https://"):
        raise ValueError("previous snapshot URL must use HTTPS")
    try:
        with urlopen(Request(url, headers={"User-Agent":"WildfireSignals/0.1"}),
                     timeout=20) as response:
            if response.status != 200:
                return None
            raw = response.read(5 * 1024 * 1024 + 1)
        if len(raw) > 5 * 1024 * 1024:
            return None
        if raw.startswith(b"\x1f\x8b"):
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as compressed:
                raw = compressed.read(100 * 1024 * 1024 + 1)
            if len(raw) > 100 * 1024 * 1024:
                return None
        snapshot = json.loads(raw)
        return snapshot if isinstance(snapshot, dict) and snapshot.get("manifest", {}).get("schema_version") == 1 else None
    except (OSError, ValueError, EOFError, json.JSONDecodeError):
        return None


def current_key(account, namespace, token):
    try:
        url = (f"{API}/accounts/{account}/storage/kv/namespaces/{namespace}/values/current")
        with urlopen(Request(url, headers={"Authorization":f"Bearer {token}"}), timeout=20) as response:
            pointer = json.load(response)
        key = pointer.get("key")
        return key if isinstance(key, str) and re.fullmatch(r"snapshot:[a-f0-9]{64}", key) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def main():
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    namespace = os.environ.get("CLOUDFLARE_KV_NAMESPACE_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    map_key = os.environ.get("FIRMS_MAP_KEY", "")
    snapshot_url = os.environ.get("PUBLIC_SNAPSHOT_URL", "")
    if not HEX_ID.fullmatch(account) or not HEX_ID.fullmatch(namespace) or not token or not map_key:
        raise RuntimeError("FIRMS key and Cloudflare Free account secrets are required")
    parsed = urlsplit(snapshot_url)
    if (parsed.scheme != "https" or not (parsed.hostname or "").endswith(".pages.dev")
            or parsed.path != "/api/snapshot" or parsed.query or parsed.fragment):
        raise RuntimeError("PUBLIC_SNAPSHOT_URL must be the free Pages HTTPS snapshot endpoint")
    verify_free(account, token)
    at = datetime.now(timezone.utc)
    previous = previous_snapshot(snapshot_url)
    firms, errors = {}, {}
    for source in FIRMS_SOURCES:
        try:
            firms[source] = fetch_firms(map_key, source, at=at)
        except (OSError, ValueError, RuntimeError, UnicodeError) as exc:
            errors[source] = type(exc).__name__
    incidents = []
    for source, fetch in (("nifc_wfigs", fetch_nifc), ("cwfis", fetch_cwfis)):
        try:
            incidents.extend(fetch(at=at))
        except (OSError, ValueError, RuntimeError) as exc:
            errors[source] = type(exc).__name__
            incidents.extend(item for item in (previous or {}).get("incidents", [])
                             if item.get("provider") == source)
    snapshot = build_snapshot(firms, incidents, at=at, previous=previous, errors=errors)

    def put(key, value, ttl):
        suffix = f"?expiration_ttl={ttl}" if ttl else ""
        api_request(f"{API}/accounts/{account}/storage/kv/namespaces/{namespace}/values/"
                    f"{quote(key, safe='')}{suffix}", token, data=value)

    key = publish(snapshot, put, previous_key=current_key(account, namespace, token))
    print(json.dumps({"key":key, "events":len(snapshot["events"]),
                      "incidents":len(snapshot["incidents"]), "errors":sorted(errors)}))


if __name__ == "__main__":
    main()
