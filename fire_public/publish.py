"""Immutable KV value followed by a pointer update, with strict size ceiling."""
import hashlib
import json

MAX_VALUE_BYTES = 20 * 1024 * 1024
TTL_SECONDS = 25 * 3600


def publish(snapshot, put):
    if snapshot.get("manifest", {}).get("schema_version") != 1:
        raise ValueError("unsupported schema")
    if snapshot["manifest"].get("truncated"):
        raise ValueError("truncated snapshot")
    payload = json.dumps(snapshot, ensure_ascii=False, allow_nan=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    if len(payload) > MAX_VALUE_BYTES:
        raise ValueError("snapshot exceeds Free-plan value budget")
    key = "snapshot:" + hashlib.sha256(payload).hexdigest()
    put(key, payload, TTL_SECONDS)
    put("current", json.dumps({"key": key}).encode("utf-8"), None)
    return key
