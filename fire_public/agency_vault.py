"""Durable offline vault of exact prospective agency receipt bytes.

Source evidence remains private, independently unverified and source-specific.
This module never creates fire labels, runs network requests, or alters collectors.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import zipfile

from .receipt_audit import _read, audit_receipts
from .history import HistoryStore
from .receipt_history import import_receipts

ROOT = Path(__file__).resolve().parents[1]
ROLE = "private_prospective_agency_source_vault"
MAX_FILES = 4096
MAX_FILE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
NAME = re.compile(r"agency-\d{8}T\d{12}Z-[a-f0-9]{16}\.json\.gz\Z")


def _private_path(path: Path) -> Path:
    """Deny public checkout, symlink escapes and false guarantees about storage."""
    path = Path(path)
    if path.is_symlink() or path.resolve().is_relative_to(ROOT):
        raise ValueError("private archive paths must be outside the public Git workspace")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("symbolic link in private archive path")
    return path


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()


def _scan(path: Path) -> dict:
    if not path.is_file() or path.is_symlink() or not NAME.fullmatch(path.name):
        raise ValueError("invalid original agency receipt filename or file type")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("oversized agency receipt")
    raw = path.read_bytes()
    doc = _read(path)
    states = doc.get("source_states")
    if (not isinstance(states, dict) or set(states) != {"cwfis", "nifc_wfigs"}
            or any(not isinstance(states[s], dict) or
                   states[s].get("status") not in {"complete", "failed", "deferred"}
                   for s in states)
            or not isinstance(doc.get("run_id"), str)
            or not re.fullmatch(r"[1-9]\d*", doc["run_id"])
            or not re.fullmatch(r"[a-f0-9]{40}", str(doc.get("head_sha", "")))
            or not re.fullmatch(r"snapshot:[a-f0-9]{64}",
                                str(doc.get("snapshot_key", "")))):
        raise ValueError("agency source states or provenance incomplete")
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("oversized agency receipt")
    return {
        "name": path.name,
        "sha256": _sha(raw),
        "bytes": len(raw),
        "scan_at": doc["scan_at"],
        "captured_at": doc["captured_at"],
        "run_id": doc["run_id"],
        "source_states": {name: states[name]["status"] for name in sorted(states)},
        "incident_count": doc["incident_count"],
    }


def _inventory(receipts: Path, *, allow_empty: bool = False) -> list[dict]:
    if not receipts.is_dir() or receipts.is_symlink():
        raise ValueError("vault receipts directory missing or symbolic link")
    paths = list(receipts.iterdir())
    if len(paths) > MAX_FILES or (not paths and not allow_empty):
        raise ValueError("vault is empty or exceeds 4096 agency receipt files")
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise ValueError("unknown or linked files inside private vault")
    if sum(p.stat().st_size for p in paths) > MAX_TOTAL_BYTES:
        raise ValueError("vault exceeds 256 MiB bounded export")
    files = [_scan(path) for path in sorted(paths)]
    index = {}
    for row in files:
        key = row["scan_at"]
        if key in index:
            raise ValueError("conflicting/duplicate agency scan UTC evidence")
        index[key] = row
    return files


def _manifest(rows: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "role": ROLE,
        "files": sorted(rows, key=lambda row: (row["scan_at"], row["name"])),
        "file_count": len(rows),
        "total_raw_gzip_bytes": sum(row["bytes"] for row in rows),
        "independent_physical_fire_identities_verified": 0,
        "extinguishment_labels_created": 0,
        "negative_fire_labels_created": 0,
        "outcome_predictions": False,
        "warning": "Archive integrity and original receipt bytes do not authenticate physical wildfire identities or outcomes.",
    }


def _vault_dir(path: Path) -> Path:
    path = _private_path(path)
    if not path.is_dir() or path.is_symlink():
        raise ValueError("private receipt vault directory does not exist")
    receipts = path / "receipts"
    if not receipts.is_dir() or receipts.is_symlink():
        raise ValueError("private vault receipts directory missing")
    extras = {x.name for x in path.iterdir()} - {"receipts", ".ingest.lock"}
    if extras:
        raise ValueError("unknown entries inside private evidence vault")
    return receipts


@contextmanager
def _lock(vault: Path):
    # Concurrent ingestion/export cannot silently give a mixed-generation view.
    lock = vault / ".ingest.lock"
    if lock.is_symlink():
        raise ValueError("unsafe private vault lock")
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "rb+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield
    finally:
        pass


def _prepare(vault: Path, *, create: bool = False) -> Path:
    vault = _private_path(vault)
    if create and not vault.exists():
        if not vault.parent.is_dir():
            raise ValueError("private vault parent directory must already exist")
        vault.mkdir(mode=0o700)
        (vault / "receipts").mkdir(mode=0o700)
    return _vault_dir(vault)


def _incoming(directory: Path) -> list[Path]:
    directory = _private_path(directory)
    if not directory.is_dir():
        raise ValueError("original receipt folder does not exist")
    files = sorted(directory.rglob("agency-*.json.gz"))
    if not files or len(files) > MAX_FILES:
        raise ValueError("no original receipts or too many agency receipts in import")
    if sum(p.stat().st_size for p in files) > MAX_TOTAL_BYTES:
        raise ValueError("incoming receipt files exceed 256 MiB")
    for file in files:
        if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(directory.resolve()):
            raise ValueError("linked or escaped receipt in incoming directory")
    return files


def ingest(vault: Path, incoming: Path) -> dict:
    """Copy genuine receipt gzip bytes; no overwrites, transaction-like rollback."""
    vault = _private_path(vault)
    incoming = _private_path(incoming)
    if vault.resolve() == incoming.resolve() or (
        vault.exists() and incoming.resolve().is_relative_to(vault.resolve())):
        raise ValueError("cannot ingest a vault into itself")
    files = _incoming(incoming)
    # Complete preflight, including collision detection within the new batch.
    proposed = {}
    by_scan = {}
    for file in files:
        row = _scan(file)
        if row["name"] in proposed:
            if proposed[row["name"]][0] != row:
                raise ValueError("same receipt name has conflicting original bytes")
            continue
        if row["scan_at"] in by_scan and by_scan[row["scan_at"]] != row:
            raise ValueError("conflicting original agency scan UTC in incoming batch")
        proposed[row["name"]] = (row, file)
        by_scan[row["scan_at"]] = row
    if not vault.exists():
        _prepare(vault, create=True)
    receipts = _vault_dir(vault)
    with _lock(vault):
        existing = _inventory(receipts, allow_empty=True)
        existing_by_name = {row["name"]: row for row in existing}
        existing_scans = {row["scan_at"]: row for row in existing}
        pending = []
        for name, (row, file) in proposed.items():
            if row["scan_at"] in existing_scans and existing_scans[row["scan_at"]] != row:
                raise ValueError("conflicting agency scan UTC already in vault")
            if name in existing_by_name:
                if existing_by_name[name] != row:
                    raise ValueError("changed original agency receipt already in vault")
                continue
            pending.append((row, file))
        if len(existing) + len(pending) > MAX_FILES or (
            sum(r["bytes"] for r in existing) + sum(r["bytes"] for r, _ in pending) >
                MAX_TOTAL_BYTES):
            raise ValueError("vault capacity exceeded")
        written = []
        try:
            for row, file in pending:
                fd, tmp = tempfile.mkstemp(prefix=".source-", dir=receipts)
                try:
                    with os.fdopen(fd, "wb") as sink, file.open("rb") as source:
                        shutil.copyfileobj(source, sink)
                        sink.flush()
                        os.fsync(sink.fileno())
                    if _sha(Path(tmp).read_bytes()) != row["sha256"]:
                        raise ValueError("original receipt changed during ingestion")
                    dest = receipts / row["name"]
                    os.link(tmp, dest)  # no overwrite, also protects concurrent source edits
                    written.append(dest)
                finally:
                    Path(tmp).unlink(missing_ok=True)
            _inventory(receipts)
        except Exception:
            for path in written:
                path.unlink()
            raise
        return {
            "vault_receipt_count": len(existing) + len(pending),
            "new_original_receipts": len(pending),
            "already_present": len(proposed) - len(pending),
            "verified_fire_outcomes": 0,
        }


def verify(vault: Path) -> dict:
    receipts = _vault_dir(vault)
    with _lock(_private_path(vault)):
        rows = _inventory(receipts)
        stats = audit_receipts(receipts)
        return {"manifest": _manifest(rows),
                "manifest_sha256": _sha(_json(_manifest(rows))),
                "source_health": stats}


def export_bundle(vault: Path, output: Path) -> dict:
    output = _private_path(output)
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("export must be a new private file in an existing directory")
    receipts = _vault_dir(vault)
    with _lock(_private_path(vault)):
        rows = _inventory(receipts)
        manifest = _manifest(rows)
        manifest_bytes = _json(manifest)
        # A ZIP is a portable byte-preserving transfer, not a source signature.
        try:
            with output.open("xb") as output_file:
                os.fchmod(output_file.fileno(), 0o600)
                with zipfile.ZipFile(output_file, "w", allowZip64=False) as bundle:
                    entries = [("manifest.json", manifest_bytes)]
                    for row in rows:
                        raw = (receipts / row["name"]).read_bytes()
                        if _sha(raw) != row["sha256"]:
                            raise ValueError("source receipt changed during export")
                        entries.append(("receipts/" + row["name"], raw))
                    for name, data in entries:
                        metadata = zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0))
                        metadata.compress_type = zipfile.ZIP_STORED  # original bytes exactly
                        metadata.external_attr = (0o100600 << 16)
                        bundle.writestr(metadata, data)
                output_file.flush()
                os.fsync(output_file.fileno())
        except Exception:
            output.unlink(missing_ok=True)
            raise
    return {"manifest_sha256": _sha(manifest_bytes),
            "bundle_sha256": _sha(output.read_bytes()),
            "receipts": len(rows), "bundle_bytes": output.stat().st_size,
            "independent_ground_truth_labels": 0}


def restore_bundle(bundle_path: Path, vault: Path) -> dict:
    bundle_path = _private_path(bundle_path)
    vault = _private_path(vault)
    if vault.exists() or not vault.parent.is_dir():
        raise ValueError("restore needs a new, private output vault directory")
    if (not bundle_path.is_file() or bundle_path.is_symlink() or
            bundle_path.stat().st_size > MAX_TOTAL_BYTES + 2 * 1024 * 1024):
        raise ValueError("invalid or oversized portable archive")
    # Strict allowlist prevents Zip Slip, extra files, forged links and zip bombs.
    with zipfile.ZipFile(bundle_path) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_FILES+1 or any(
                z.is_dir() or z.flag_bits & 0x1 or
                z.file_size > (3 * 1024 * 1024 if z.filename == "manifest.json" else MAX_FILE_BYTES) or
                z.compress_type != zipfile.ZIP_STORED
                for z in entries):
            raise ValueError("unsafe or oversized portable archive entry")
        names = [z.filename for z in entries]
        if len(set(names)) != len(names) or "manifest.json" not in names:
            raise ValueError("portable archive has duplicate or missing manifest")
        manifest_raw = archive.read("manifest.json")
        if len(manifest_raw) > 3*1024*1024:
            raise ValueError("oversized vault manifest")
        manifest = json.loads(manifest_raw)
        if not isinstance(manifest, dict) or manifest.get("role") != ROLE or manifest.get("schema_version") != 1:
            raise ValueError("unrecognized private evidence manifest")
        rows = manifest.get("files")
        if (not isinstance(rows, list) or not rows or len(rows)>MAX_FILES or
                manifest.get("file_count")!=len(rows)):
            raise ValueError("invalid manifest contents")
        expected = {"manifest.json"}
        for row in rows:
            if not isinstance(row,dict) or not isinstance(row.get("name"),str) or not NAME.fullmatch(row["name"]):
                raise ValueError("unsafe manifest source filename")
            expected.add("receipts/"+row["name"])
        if set(names)!=expected or len(expected)!=len(names):
            raise ValueError("manifest does not describe exactly the original source files")
        if sum(r.get("bytes",0) for r in rows)!=manifest.get("total_raw_gzip_bytes"):
            raise ValueError("manifest byte tally mismatch")
        if manifest.get("extinguishment_labels_created")!=0 or manifest.get("negative_fire_labels_created")!=0:
            raise ValueError("original evidence cannot contain verified labels")
        vault.mkdir(mode=0o700)
        receipts=(vault/"receipts")
        receipts.mkdir(mode=0o700)
        try:
            for row in rows:
                raw=archive.read("receipts/"+row["name"])
                if len(raw)!=row["bytes"] or _sha(raw)!=row["sha256"]:
                    raise ValueError("source bytes differ from portable manifest")
                target=receipts/row["name"]
                with target.open("xb") as f:
                    os.fchmod(f.fileno(),0o600)
                    f.write(raw)
                    f.flush()
                    os.fsync(f.fileno())
                if _scan(target)!=row:
                    raise ValueError("restored receipt metadata mismatch")
            if _manifest(_inventory(receipts))!=manifest:
                raise ValueError("restored manifest differs from source evidence")
        except Exception:
            shutil.rmtree(vault)
            raise
    return {"restored_receipts":len(rows),"manifest_sha256":_sha(manifest_raw),
            "verified_fire_outcomes":0}


def rebuild_sqlite(vault: Path, output: Path) -> dict:
    """Rebuild the existing as-of HistoryStore only from vault source receipts."""
    output = _private_path(output)
    if output.exists() or not output.parent.is_dir() or output.parent.is_symlink():
        raise ValueError("database must be a new private output file")
    receipts = _vault_dir(vault)
    with _lock(_private_path(vault)):
        rows = _inventory(receipts)
        with tempfile.TemporaryDirectory(prefix=".agency-restore-",dir=output.parent) as temp:
            stage = Path(temp)/"evidence.sqlite3"
            store = HistoryStore(stage)
            try:
                details = import_receipts(store, receipts)
                integrity = store.connection.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok" or details["imported_scans"] != len(rows):
                    raise ValueError("source replay integrity check failed")
            finally:
                store.close()
            os.chmod(stage,0o600)
            os.link(stage, output)
    return {"source_receipts_replayed":len(rows),
            "historical_scans": details["imported_scans"],
            "sqlite_integrity": "ok",
            "extinguishment_labels_created":0}



def research_workspace(vault: Path, output: Path, *, at: str | None = None,
                       provider: str | None = None,
                       official_id: str | None = None) -> dict:
    """Rebuild source evidence inside a temporary database, then ship offline UI.

    The temporary SQLite is removed after rendering. No source evidence,
    reviewer notes, or locally reconstructed DB is uploaded anywhere.
    """
    from .prospective_replay import replay, open_archive, _write_private

    output = _private_path(output)
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("workspace must be a new directory in an existing private parent")
    if official_id is not None and provider is None:
        raise ValueError("exact official agency ID requires provider")
    with tempfile.TemporaryDirectory(prefix=".agency-workspace-", dir=output.parent) as stage:
        scratch=Path(stage)/"recovered.sqlite3"
        reconstructed=rebuild_sqlite(vault, scratch)
        db=open_archive(scratch)
        try:
            cutoff=at
            if cutoff is None:
                row=db.execute("SELECT MAX(captured_at) FROM receipt_scans").fetchone()
                if not row or not row[0]:
                    raise ValueError("archive has no prospective agency receipt times")
                cutoff=row[0]
            report=replay(db,at=cutoff,provider=provider,official_id=official_id)
        finally:
            db.close()
        _write_private(output,report)
    return {
        "source_receipts_replayed": reconstructed["source_receipts_replayed"],
        "historical_scans": reconstructed["historical_scans"],
        "cases": report["known_source_identities"],
        "as_of": report["as_of"],
        "output_files": ["index.html","evidence.json"],
        "verified_fire_outcomes":0,
    }


def main() -> None:
    parser=argparse.ArgumentParser(description="Durable private agency evidence ingestion, verification, export and disaster recovery")
    sub=parser.add_subparsers(dest="command",required=True)
    a=sub.add_parser("ingest");a.add_argument("--vault",type=Path,required=True)
    a.add_argument("--input",type=Path,required=True)
    a=sub.add_parser("verify");a.add_argument("--vault",type=Path,required=True)
    a=sub.add_parser("export");a.add_argument("--vault",type=Path,required=True)
    a.add_argument("--output",type=Path,required=True)
    a=sub.add_parser("restore");a.add_argument("--bundle",type=Path,required=True)
    a.add_argument("--vault",type=Path,required=True)
    a=sub.add_parser("rebuild");a.add_argument("--vault",type=Path,required=True)
    a.add_argument("--db",type=Path,required=True)
    a=sub.add_parser("workspace");a.add_argument("--vault",type=Path,required=True)
    a.add_argument("--output-dir",type=Path,required=True)
    a.add_argument("--at")
    a.add_argument("--provider",choices=["cwfis","nifc_wfigs"])
    a.add_argument("--official-id")
    args=parser.parse_args()
    if args.command=="ingest":result=ingest(args.vault,args.input)
    elif args.command=="verify":result=verify(args.vault)
    elif args.command=="export":result=export_bundle(args.vault,args.output)
    elif args.command=="restore":result=restore_bundle(args.bundle,args.vault)
    elif args.command=="rebuild":result=rebuild_sqlite(args.vault,args.db)
    else:result=research_workspace(args.vault,args.output_dir,at=args.at,
                                   provider=args.provider,official_id=args.official_id)
    print(json.dumps(result,sort_keys=True,ensure_ascii=False))


if __name__=="__main__":
    main()
