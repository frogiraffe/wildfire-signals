"""Atomic compressed scan receipts for individual FIRMS thermal detections."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .collect import FIRMS_SOURCES


class PixelArchive:
    def __init__(self, directory: Path, *, at: datetime):
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timezone-aware scan time required")
        self.directory = directory
        self.at = at.astimezone(timezone.utc)
        self.count = 0
        self.path = None

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".firms-pixels-", dir=self.directory)
        self._temp = Path(name)
        self._file = os.fdopen(fd, "wb")
        self._gzip = gzip.GzipFile(fileobj=self._file, mode="wb", mtime=0, filename="")
        return self

    def append(self, record: dict) -> None:
        line = json.dumps(record, sort_keys=True, ensure_ascii=False,
                          allow_nan=False, separators=(",", ":")).encode() + b"\n"
        self._gzip.write(line)
        self.count += 1

    def __exit__(self, error_type, error, traceback):
        try:
            self._gzip.close()
            self._file.close()
            if error_type is None and self.count:
                digest = hashlib.sha256(self._temp.read_bytes()).hexdigest()[:16]
                stamp = self.at.strftime("%Y%m%dT%H%M%SZ")
                self.path = self.directory / f"firms-pixels-{stamp}-{digest}.jsonl.gz"
                os.link(self._temp, self.path)
        finally:
            self._temp.unlink(missing_ok=True)
        return False


def write_scan_receipt(snapshot: dict, directory: Path, snapshot_key: str) -> Path:
    """Keep empty and failed source attempts distinguishable in the artifact set."""
    if not re.fullmatch(r"snapshot:[a-f0-9]{64}", snapshot_key):
        raise ValueError("invalid snapshot key")
    scan_at = datetime.fromisoformat(snapshot["manifest"]["last_scan_at"])
    if scan_at.tzinfo is None or scan_at.utcoffset() is None:
        raise ValueError("scan time must be timezone-aware")
    stamp = scan_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    states = {row["key"]:row["status"] for row in snapshot["sources"]
              if row.get("key") in FIRMS_SOURCES}
    if set(states) != set(FIRMS_SOURCES):
        raise ValueError("FIRMS source states incomplete")
    files = [{"name":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
             for path in sorted(directory.glob(f"firms-pixels-{stamp}-*.jsonl.gz"))]
    receipt = {"schema_version":1,"role":"firms_pixel_scan_receipt",
               "scan_at":scan_at.astimezone(timezone.utc).isoformat(),
               "captured_at":datetime.now(timezone.utc).isoformat(),
               "snapshot_key":snapshot_key,"source_states":states,
               "pixel_files":files}
    payload = gzip.compress(json.dumps(receipt, sort_keys=True,
        separators=(",", ":")).encode(), mtime=0)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"firms-pixel-scan-{stamp}-{hashlib.sha256(payload).hexdigest()[:16]}.json.gz"
    fd, temp = tempfile.mkstemp(prefix=".firms-scan-", dir=directory)
    try:
        with os.fdopen(fd,"wb") as output:
            output.write(payload)
        os.link(temp,path)
    finally:
        Path(temp).unlink(missing_ok=True)
    return path
