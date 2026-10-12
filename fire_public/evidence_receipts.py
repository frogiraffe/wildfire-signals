"""Immutable local evidence byte receipts and reviewer-to-source binding audit.

This stores *operator-supplied* file bytes, not authenticated external truth.
No arbitrary URL fetching (avoids SSRF), no public upload, no non-fire inference.
Only receipt files whose SHA-256 still matches private archived blobs qualify
for the optional strict independent-review export gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path

from .label_review import _load, _sha, _text, _url, _utc, MAX_REVIEW_BYTES

MAX_BLOB_BYTES = 5 * 1024 * 1024
MAX_INDEX = 1_600
MAX_METADATA_BYTES = 32_768
ROLES = ("label", "primary", "secondary", "coverage")
HEX = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def _source(meta: dict) -> dict:
    if meta.get("schema_version") != 1:
        raise ValueError("source evidence metadata schema_version 1 required")
    case_id = _text(meta.get("case_id"), "case identity")
    role = meta.get("role")
    if role not in ROLES:
        raise ValueError("source receipt role must be label, primary, secondary, or coverage")
    if not _url(meta.get("source_url")) or not _url(meta.get("rights_url")):
        raise ValueError("source and licensing HTTPS URLs required")
    source_kind = _text(meta.get("source_kind"), "evidence source kind", 8)
    if source_kind.casefold() in ("firms", "satellite_candidate",
                                  "thermal_detection", "fire_perimeter_absence"):
        raise ValueError("source kind is not independently verified fire ground truth")
    source_record = _text(meta.get("source_record_id"), "provider record identifier")
    published_at = _utc(_text(meta.get("source_published_at"), "source published at"))
    data = {
        "schema_version": 1,
        "case_id": case_id,
        "role": role,
        "source_url": meta["source_url"],
        "rights_url": meta["rights_url"],
        "source_kind": source_kind,
        "source_record_id": source_record,
        "source_published_at": published_at.isoformat(),
        "source_authenticity_independently_verified": False,
        "claim_kind": "operator_supplied_local_source_snapshot",
    }
    if role == "coverage":
        start = _utc(_text(meta.get("coverage_start_at"), "coverage start"))
        end = _utc(_text(meta.get("coverage_end_at"), "coverage end"))
        if start >= end:
            raise ValueError("source coverage interval must have positive duration")
        data.update(coverage_region_id=_text(
                        meta.get("coverage_region_id"), "coverage region"),
                    coverage_start_at=start.isoformat(),
                    coverage_end_at=end.isoformat(),
                    coverage_attestation="declared_scope_not_externally_verified")
    elif "coverage_start_at" in meta or "coverage_end_at" in meta:
        raise ValueError("source coverage window only valid for coverage receipt")
    return data


def _read_small_blob(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BLOB_BYTES:
        raise ValueError("evidence snapshot must be an existing regular file <=5 MiB")
    blob = path.read_bytes()
    if not blob:
        raise ValueError("empty evidence source snapshot cannot support adjudication")
    return blob


def _archive_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("archive path cannot be a symlink")
    try:
        with path.open("xb") as stream:
            stream.write(data)
    except FileExistsError:
        if path.is_symlink() or not path.is_file() or path.read_bytes() != data:
            raise ValueError("existing archive object conflicts with supplied evidence")
    # Content-addressed object name and sha digest are checked on all later reads.


def capture(blob_path: Path, metadata_path: Path, store: Path,
            *, captured_at: str | None = None) -> dict:
    """Archive exact bytes and operator claims with deterministic receipt identity."""
    if metadata_path.is_symlink() or not metadata_path.is_file() or (
            metadata_path.stat().st_size > MAX_METADATA_BYTES):
        raise ValueError("small, regular metadata JSON file required")
    meta = _source(_load(metadata_path, MAX_METADATA_BYTES))
    data = _read_small_blob(blob_path)
    received = _utc(captured_at or datetime.now().astimezone().isoformat())
    if received < _utc(meta["source_published_at"]):
        raise ValueError("cannot capture a source before its declared publication")
    digest = hashlib.sha256(data).hexdigest()
    receipt = {
        **meta, "captured_at": received.isoformat(),
        "blob_sha256": digest, "blob_bytes": len(data),
    }
    identity = hashlib.sha256(_canonical(receipt)).hexdigest()
    receipt["receipt_id"] = identity
    if not store.exists() or not store.is_dir() or store.is_symlink():
        raise ValueError("create a private regular evidence archive directory first")
    if any(p.resolve().is_relative_to(store.resolve()) for p in (blob_path, metadata_path)):
        raise ValueError("input sources must live outside evidence store")
    # The byte object is immutable under its digest. A failed receipt write can
    # leave an orphaned byte object; it is not a valid indexed receipt.
    _archive_new(store / "blobs" / (digest + ".bin"), data)
    _archive_new(store / "receipts" / (identity + ".json"), _canonical(receipt))
    return receipt


def _store_receipts(store: Path) -> tuple[dict, str]:
    if store.is_symlink() or not store.is_dir():
        raise ValueError("private evidence store directory required")
    root = store / "receipts"
    if root.is_symlink() or not root.is_dir():
        raise ValueError("private evidence receipt directory required")
    files = sorted(root.iterdir())
    if len(files) > MAX_INDEX:
        raise ValueError("receipt audit budget exceeded 1600 records")
    receipts = {}
    signature = hashlib.sha256()
    for path in files:
        if (path.is_symlink() or not path.is_file() or
                path.suffix != ".json" or not HEX.fullmatch(path.stem) or
                path.stat().st_size > MAX_METADATA_BYTES):
            raise ValueError("invalid receipt archive member")
        r = _load(path, MAX_METADATA_BYTES)
        claimed_id = r.pop("receipt_id", None)
        if claimed_id != path.stem or hashlib.sha256(_canonical(r)).hexdigest() != claimed_id:
            raise ValueError("source receipt content integrity mismatch")
        _source(r)
        data_sha = r.get("blob_sha256")
        size = r.get("blob_bytes")
        if not isinstance(data_sha, str) or not HEX.fullmatch(data_sha):
            raise ValueError("invalid archived source SHA-256")
        if type(size) is not int or not 0 < size <= MAX_BLOB_BYTES:
            raise ValueError("invalid source snapshot byte length")
        blob_path = store / "blobs" / (data_sha + ".bin")
        if blob_path.is_symlink():
            raise ValueError("archive blob cannot be symlink")
        blob = _read_small_blob(blob_path)
        if len(blob) != size or hashlib.sha256(blob).hexdigest() != data_sha:
            raise ValueError("source snapshot SHA-256 or byte length mismatch")
        r["receipt_id"] = claimed_id
        receipts[claimed_id] = r
        signature.update(_canonical(r))
    return receipts, signature.hexdigest()


def audit_receipts(queue_path: Path, reviews_path: Path, store: Path) -> dict:
    """Connect each *adjudicated* review to an actual hash-checked source file.

    A reviewer may have inspected real records, but an URL alone does not
    prove the bytes or any declaration. Missing/ambiguous receipts fail
    strict finalization, while the offline audit describes the deficit.
    """
    queue = _load(queue_path, MAX_REVIEW_BYTES)
    reviews = _load(reviews_path, MAX_REVIEW_BYTES)
    if reviews.get("queue_sha256") != _sha(queue_path):
        raise ValueError("review decisions do not match exact queue bytes")
    cases = queue.get("cases")
    entries = reviews.get("decisions")
    if not isinstance(cases, list) or not isinstance(entries, list):
        raise ValueError("review queue and decisions required")
    by_case = {item["case_id"]: item for item in cases}
    if len(by_case) != len(cases) or len(entries) != len(cases):
        raise ValueError("each unique case requires a decision")
    by_decision = {item["case_id"]: item for item in entries}
    if len(by_decision) != len(entries) or set(by_decision) != set(by_case):
        raise ValueError("review decisions must cover every queued case exactly")
    receipts, store_sha = _store_receipts(store)
    indexed: dict[tuple[str, str, str], list[dict]] = {}
    for r in receipts.values():
        indexed.setdefault((r["case_id"], r["role"], r["source_url"]), []).append(r)
        if r["case_id"] not in by_case:
            raise ValueError("orphan source evidence receipt does not belong to queue")
    bindings = []
    failures = []
    for case in cases:
        entry = by_decision[case["case_id"]]
        if entry.get("status") != "adjudicated":
            continue
        required = [("label", entry.get("label_evidence_url"),
                     entry.get("label_verified_at")),
                    ("primary", (entry.get("primary") or {}).get("evidence_url"),
                     (entry.get("primary") or {}).get("reviewed_at")),
                    ("secondary", (entry.get("secondary") or {}).get("evidence_url"),
                     (entry.get("secondary") or {}).get("reviewed_at"))]
        if entry.get("label") == 0:
            cov = entry.get("negative_coverage") or {}
            required.append(("coverage", cov.get("completeness_evidence_url"),
                             cov.get("reviewed_at")))
        for role, url, reviewed_at in required:
            key = (case["case_id"], role, url)
            matches = indexed.get(key, [])
            if len(matches) != 1:
                failures.append({"case_id":case["case_id"], "role":role,
                                 "reason":"missing_or_ambiguous_source_snapshot"})
                continue
            r = matches[0]
            published = _utc(r["source_published_at"])
            captured = _utc(r["captured_at"])
            reviewed = _utc(reviewed_at)
            if published > captured or captured > reviewed:
                failures.append({"case_id":case["case_id"], "role":role,
                                 "reason":"source_not_captured_by_review_time"})
                continue
            if role == "label" and r["source_record_id"] != entry.get("label_source_id"):
                failures.append({"case_id":case["case_id"], "role":role,
                                 "reason":"source_record_does_not_match_reviewed_label"})
                continue
            if role == "coverage":
                cov = entry["negative_coverage"]
                if (r["coverage_region_id"] != entry.get("region_id")
                        or r["source_kind"].casefold() in ("nifc_historical_perimeter", "firms")
                        or _utc(r["coverage_start_at"]) > _utc(cov["start_at"])
                        or _utc(r["coverage_end_at"]) < _utc(cov["end_at"])):
                    failures.append({"case_id":case["case_id"], "role":role,
                                     "reason":"scope_does_not_support_declared_negative_window"})
                    continue
            bindings.append({
                "case_id":case["case_id"], "role":role,
                "receipt_id":r["receipt_id"], "blob_sha256":r["blob_sha256"],
                "source_url":r["source_url"], "source_kind":r["source_kind"],
                "source_published_at":r["source_published_at"],
                "captured_at":r["captured_at"],
            })
    return {
        "schema_version": 1,
        "queue_sha256": _sha(queue_path),
        "reviews_sha256": _sha(reviews_path),
        "source_receipts_sha256": store_sha,
        "archived_source_snapshots": len(receipts),
        "review_bindings": sorted(bindings, key=lambda x:(x["case_id"],x["role"])),
        "missing_or_invalid": failures,
        "structurally_receipt_complete": len(failures) == 0 and bool(bindings),
        "source_authenticity_externally_verified": False,
        "independent_fire_negative_truth_verified": False,
        "notes": [
            "Receipt hashes verify operator-supplied bytes, NOT HTTPS origin or authenticity.",
            "HTTPS URLs are reviewer-declared and never fetched by this offline tool.",
            "A coverage interval is operator-declared; it cannot prove no fire by itself.",
            "No FIRMS or missing official perimeter becomes a wildfire negative.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline private wildfire label source receipts")
    sub = parser.add_subparsers(dest="action", required=True)
    capture_cmd = sub.add_parser("capture")
    capture_cmd.add_argument("--blob", required=True, type=Path)
    capture_cmd.add_argument("--metadata", required=True, type=Path)
    capture_cmd.add_argument("--store", required=True, type=Path)
    audit_cmd = sub.add_parser("audit")
    audit_cmd.add_argument("--queue", required=True, type=Path)
    audit_cmd.add_argument("--reviews", required=True, type=Path)
    audit_cmd.add_argument("--store", required=True, type=Path)
    audit_cmd.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.action == "capture":
        print(json.dumps(capture(args.blob,args.metadata,args.store),
                         ensure_ascii=False, sort_keys=True))
    else:
        if args.output.exists() or args.output.resolve() in {
                args.queue.resolve(), args.reviews.resolve()}:
            parser.error("audit report must not overwrite research inputs")
        result = audit_receipts(args.queue,args.reviews,args.store)
        _archive_new(args.output, json.dumps(
            result, ensure_ascii=False, sort_keys=True, indent=2).encode() + b"\n")
        print(json.dumps({"ready":result["structurally_receipt_complete"],
                          "missing":len(result["missing_or_invalid"]),
                          "report":str(args.output)},sort_keys=True))


if __name__ == "__main__":
    main()
