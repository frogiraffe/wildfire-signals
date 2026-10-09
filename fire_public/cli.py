"""Hourly collector; refuses to write before a Free subscription check."""
import json
import os
import re
from datetime import datetime, timezone
from urllib.parse import quote
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
    result = api_request(f"{API}/accounts/{account}/subscriptions", token).get("result")
    if not isinstance(result, list) or not result:
        raise RuntimeError("Cloudflare subscription could not be verified")
    for item in result:
        if item.get("state") in {"Cancelled", "Expired", "Failed"}:
            continue
        if (item.get("rate_plan") or {}).get("id") not in {"free", "partners_free"} or (
                item.get("price") not in {None, 0}):
            raise RuntimeError("paid or unknown Cloudflare subscription; refusing publication")


def previous_snapshot(url):
    if not url:
        return None
    if not url.startswith("https://"):
        raise ValueError("previous snapshot URL must use HTTPS")
    try:
        with urlopen(Request(url, headers={"User-Agent":"FireMonitorPublic/0.1"}),
                     timeout=20) as response:
            if response.status != 200:
                return None
            raw = response.read(20 * 1024 * 1024 + 1)
        if len(raw) > 20 * 1024 * 1024:
            return None
        snapshot = json.loads(raw)
        return snapshot if snapshot.get("manifest", {}).get("schema_version") == 1 else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def main():
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    namespace = os.environ.get("CLOUDFLARE_KV_NAMESPACE_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    map_key = os.environ.get("FIRMS_MAP_KEY", "")
    if not HEX_ID.fullmatch(account) or not HEX_ID.fullmatch(namespace) or not token or not map_key:
        raise RuntimeError("FIRMS key and Cloudflare Free account secrets are required")
    verify_free(account, token)
    at = datetime.now(timezone.utc)
    previous = previous_snapshot(os.environ.get("PUBLIC_SNAPSHOT_URL", ""))
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

    key = publish(snapshot, put)
    print(json.dumps({"key":key, "events":len(snapshot["events"]),
                      "incidents":len(snapshot["incidents"]), "errors":sorted(errors)}))


if __name__ == "__main__":
    main()
