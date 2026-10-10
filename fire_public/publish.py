"""Immutable KV value followed by a pointer update, with strict size ceiling."""
import hashlib
import gzip
import json

MAX_VALUE_BYTES = 5 * 1024 * 1024
TTL_SECONDS = 7 * 24 * 3600


def publish(snapshot, put, *, previous_key=None):
    if snapshot.get("manifest", {}).get("schema_version") != 1:
        raise ValueError("unsupported schema")
    if snapshot["manifest"].get("truncated"):
        raise ValueError("truncated snapshot")
    raw = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    payload = gzip.compress(raw, compresslevel=6, mtime=0)
    if len(payload) > MAX_VALUE_BYTES:
        raise ValueError("snapshot exceeds Free-plan value budget")
    key = "snapshot:" + hashlib.sha256(raw).hexdigest()
    put(key, payload, TTL_SECONDS)
    pointer = {"key": key, "last_scan_at": snapshot["manifest"]["last_scan_at"]}
    if previous_key and previous_key.startswith("snapshot:") and previous_key != key:
        pointer["previous_key"] = previous_key
    put("current", json.dumps(pointer).encode("utf-8"), None)
    return key
