"""Hourly collector; refuses to write before a Free subscription check."""
import json
import gzip
import io
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .collect import FIRMS_SOURCES, build_snapshot, fetch_cwfis, fetch_firms, fetch_nifc
from .publish import publish
from .analysis_receipt import build_receipt, write_receipt

API = "https://api.cloudflare.com/client/v4"
HEX_ID = re.compile(r"^[a-f0-9]{32}$")
MIN_SCAN_INTERVAL = timedelta(minutes=55)


def maybe_write_analysis_receipt(snapshot, snapshot_key, *, scan_at, captured_at=None):
    if os.environ.get("ENABLE_ANALYSIS_ARCHIVE") != "true":
        return {"status": "disabled"}
    if os.environ.get("FORCE_COLLECTION") == "true":
        return {"status": "manual_repair_excluded"}
    if scan_at.hour not in {0, 6, 12, 18} or scan_at.minute < 17:
        return {"status": "outside_pilot_window"}
    try:
        payload, report = build_receipt(snapshot,
            captured_at=(captured_at or datetime.now(timezone.utc)).isoformat(),
            run_id=os.environ.get("GITHUB_RUN_ID", ""),
            head_sha=os.environ.get("GITHUB_SHA", ""),
            snapshot_key=snapshot_key)
        write_receipt(Path(os.environ["ANALYSIS_RECEIPT_DIR"]),payload,
                      scan_at=report["scan_at"])
        return {"status": "written", **report}
    except Exception as exc:
        # Publication already succeeded; an optional research receipt cannot
        # invalidate or roll back the public map. The skip stays in the run log.
        return {"status": "skipped", "reason": str(exc) if isinstance(exc, ValueError)
                else type(exc).__name__}


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


def verify_free(account, token, *, attested_account=""):
    payload = api_request(f"{API}/accounts/{account}/subscriptions", token)
    result = payload.get("result")
    info = payload.get("result_info") or {}
    page, per_page = info.get("page"), info.get("per_page")
    valid_number = lambda value: isinstance(value, int) and not isinstance(value, bool)
    if (not valid_number(page) or not valid_number(per_page)
            or page != 1 or per_page < 1):
        raise RuntimeError("cannot verify every Cloudflare subscription page")
    if "next_page" in info and "count" not in info and "total_count" not in info:
        complete = info["next_page"] is None or info["next_page"] is False
    else:
        count, total_count = info.get("count"), info.get("total_count")
        complete = (valid_number(count) and valid_number(total_count)
                    and count == total_count and total_count <= per_page)
    if not complete:
        raise RuntimeError("cannot verify every Cloudflare subscription page")
    if not isinstance(result, list) or (not result and attested_account != account):
        raise RuntimeError("Cloudflare subscription could not be verified")
    if not result:
        return
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
        with urlopen(Request(url, headers={"User-Agent":"WildfireSignals/0.1",
                                          "Accept-Encoding":"gzip"}),
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


def current_pointer(account, namespace, token):
    url = f"{API}/accounts/{account}/storage/kv/namespaces/{namespace}/values/current"
    try:
        with urlopen(Request(url, headers={"Authorization":f"Bearer {token}"}), timeout=20) as response:
            pointer = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            namespace_url = f"{API}/accounts/{account}/storage/kv/namespaces/{namespace}"
            details = api_request(namespace_url, token).get("result")
            if not isinstance(details, dict) or details.get("id") != namespace:
                raise RuntimeError("Cloudflare KV namespace could not be verified") from exc
            return None
        raise
    if (not isinstance(pointer, dict) or not isinstance(pointer.get("key"), str)
            or not re.fullmatch(r"snapshot:[a-f0-9]{64}", pointer["key"])):
        raise RuntimeError("current snapshot pointer is invalid")
    return pointer


def scan_time(value, at):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("scan timestamp lacks timezone")
    parsed = parsed.astimezone(timezone.utc)
    if parsed > at:
        raise ValueError("scan timestamp is in the future")
    return parsed


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
    verify_free(account, token,
                attested_account=os.environ.get("CLOUDFLARE_FREE_ATTESTED_ACCOUNT_ID", ""))
    at = datetime.now(timezone.utc)
    previous = previous_snapshot(snapshot_url)
    force = os.environ.get("FORCE_COLLECTION") == "true"
    pointer = current_pointer(account, namespace, token)
    times = []
    if previous is not None:
        try:
            times.append(scan_time(previous["manifest"]["last_scan_at"], at))
        except (KeyError, TypeError, ValueError, AttributeError):
            previous = None  # Invalid cached history must not enter build_snapshot.
    if pointer is not None and "last_scan_at" in pointer:
        try:
            times.append(scan_time(pointer["last_scan_at"], at))
        except (TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError("current snapshot pointer timestamp is invalid") from exc
    scan_at = max(times) if times else None
    age = at - scan_at if scan_at else None
    if not force:
        if previous is None and pointer is None:
            age = MIN_SCAN_INTERVAL  # Empty namespace: first scheduled run may seed it.
        if age is None or age < timedelta(0):
            print(json.dumps({"skipped":"unverified_previous_snapshot"}))
            return
        if age < MIN_SCAN_INTERVAL:
            print(json.dumps({"skipped":"recent_snapshot", "last_scan_at":scan_at.isoformat()}))
            return
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

    key = publish(snapshot, put, previous_key=pointer["key"] if pointer else None)
    receipt = maybe_write_analysis_receipt(snapshot,key,scan_at=at)
    print(json.dumps({"key":key, "events":len(snapshot["events"]),
                      "incidents":len(snapshot["incidents"]), "errors":sorted(errors),
                      "analysis_receipt":receipt}))


if __name__ == "__main__":
    main()
