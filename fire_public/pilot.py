"""Source-only prospective measurements; never writes to Cloudflare."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

from . import collect
from .publish import MAX_VALUE_BYTES


def measure(*, at: datetime, key: str) -> dict:
    if not key:
        raise ValueError("FIRMS_MAP_KEY missing")
    report = {"at":at.isoformat(), "sources":{}, "publication_attempted":False}
    firms = {}
    incidents = []
    errors = {}
    original_get = collect._get

    def run(source, operation):
        requests = downloaded = 0

        def measured_get(url):
            nonlocal requests, downloaded
            requests += 1
            data = original_get(url)
            downloaded += len(data)
            return data

        collect._get = measured_get
        wall_start, cpu_start = time.perf_counter(), time.process_time()
        status, value, error = "complete", [], None
        try:
            value = operation()
        except Exception as exc:
            status = "deferred" if isinstance(exc, collect.SourceDeferred) else "failed"
            error = type(exc).__name__
            errors[source] = error
        finally:
            collect._get = original_get
        report["sources"][source] = {"status":status, "error_type":error,
            "known_http_requests":requests, "downloaded_bytes":downloaded,
            "records":len(value), "wall_seconds":round(time.perf_counter() - wall_start,3),
            "cpu_seconds":round(time.process_time() - cpu_start,3)}
        return value

    for source in collect.FIRMS_SOURCES:
        firms[source] = run(source, lambda source=source: collect.fetch_firms(key,source,at=at))
    incidents.extend(run("nifc_wfigs",lambda:collect.fetch_nifc(at=at)))
    incidents.extend(run("cwfis",lambda:collect.fetch_cwfis(at=at)))
    if len(errors) < len(collect.FIRMS_SOURCES) + 2:
        snapshot = collect.build_snapshot(firms,incidents,at=at,errors=errors)
        import gzip
        raw = json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(",", ":")).encode()
        report["candidate_count"] = len(snapshot["events"])
        report["agency_count"] = len(snapshot["incidents"])
        report["provisional_match_count"] = len(snapshot["matches"])
        report["snapshot_raw_bytes"] = len(raw)
        report["snapshot_gzip_bytes"] = len(gzip.compress(raw,compresslevel=6,mtime=0))
        report["within_kv_value_budget"] = report["snapshot_gzip_bytes"] <= MAX_VALUE_BYTES
    else:
        report["data_status"] = "all_sources_failed"
    return report


def main() -> None:
    key = os.environ.get("FIRMS_MAP_KEY", "")
    result = measure(at=datetime.now(timezone.utc), key=key)
    print(json.dumps(result,sort_keys=True,separators=(",", ":")))


if __name__ == "__main__":
    main()
