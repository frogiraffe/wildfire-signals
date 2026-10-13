"""Explicit local pull of expiring GitHub Actions *agency* source receipts.

No scheduled execution, cloud backup, production collector changes or third-party
uploads. Preserve only original NIFC/CWFIS agency receipt bytes in private vault.
"""
from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone, timedelta
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
import zipfile

from .agency_vault import _private_path, _prepare, _scan, _inventory, ingest, verify
from .analysis_receipt import MAX_COMPRESSED_BYTES
from .history import _timestamp
from .receipt_audit import _read

REPO = "frogiraffe/wildfire-signals"
BASE = f"https://api.github.com/repos/{REPO}"
WORKFLOW = ".github/workflows/collect.yml"
ARTIFACT_NAME = re.compile(r"analysis-receipt-([1-9]\d*)-([1-9]\d*)\Z")
RECEIPT_NAME = re.compile(r"agency-\d{8}T\d{12}Z-[a-f0-9]{16}\.json\.gz\Z")
MAX_DOWNLOAD = 100 * 1024 * 1024
MAX_METADATA = 2 * 1024 * 1024
MAX_ENTRIES = 10000
PER_PAGE = 100


class _NeverFollowRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _artifact_host(url: str) -> bool:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    return (parsed.scheme == "https" and not parsed.username and
            not parsed.password and parsed.port in (None, 443) and
            (host.endswith(".blob.core.windows.net")
             or host == "pipelines.actions.githubusercontent.com"
             or host.endswith(".actions.githubusercontent.com")))


class GitHubArtifacts:
    """Read-only GitHub REST connector; never forwards the token to ZIP hosting."""
    def __init__(self, token: str):
        if not isinstance(token, str) or not token.strip():
            raise ValueError("a read-only GH_TOKEN or GITHUB_TOKEN is required")
        self._token = token.strip()
        self._opener = build_opener(_NeverFollowRedirects())

    def _read(self, request: Request, cap: int, *, allow_redirect=False) -> bytes | str:
        try:
            with self._opener.open(request, timeout=45) as response:
                if response.status != 200:
                    raise RuntimeError("unexpected GitHub response status")
                raw = response.read(cap + 1)
        except HTTPError as error:
            if allow_redirect and error.code in (301, 302, 303, 307, 308):
                location = error.headers.get("Location")
                if not isinstance(location, str) or not _artifact_host(location):
                    raise ValueError("untrusted GitHub Actions artifact redirect") from None
                # Fresh request: NEVER reuse the API Authorization header.
                return location
            raise RuntimeError(f"GitHub API request failed with HTTP {error.code}") from None
        if len(raw) > cap:
            raise ValueError("GitHub API response exceeds byte budget")
        return raw

    def _api(self, suffix: str) -> dict:
        if not suffix.startswith("/") or ".." in suffix or "://" in suffix:
            raise ValueError("invalid GitHub API path")
        request = Request(BASE + suffix, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "wildfire-signals-private-evidence-sync",
        })
        raw = self._read(request, MAX_METADATA)
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("invalid GitHub metadata")
        return result

    def list_artifacts(self, page: int) -> dict:
        return self._api(f"/actions/artifacts?per_page={PER_PAGE}&page={page}")

    def get_run(self, run_id: int) -> dict:
        if not isinstance(run_id, int) or not 0 < run_id < 10**20:
            raise ValueError("invalid GitHub Actions run")
        return self._api(f"/actions/runs/{run_id}")

    def download_zip(self, artifact_id: int) -> bytes:
        if not isinstance(artifact_id, int) or not 0 < artifact_id < 10**20:
            raise ValueError("invalid GitHub Actions artifact ID")
        url = BASE + f"/actions/artifacts/{artifact_id}/zip"
        request = Request(url, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "wildfire-signals-private-evidence-sync",
        })
        result = self._read(request, MAX_DOWNLOAD, allow_redirect=True)
        if isinstance(result, bytes):
            return result
        # Signed URLs may expire: abort instead of following other redirects.
        return self._read(Request(result, headers={
            "User-Agent": "wildfire-signals-private-evidence-sync",
        }), MAX_DOWNLOAD)


def _time(raw: str) -> datetime:
    return datetime.fromisoformat(_timestamp(raw))


def _artifact(row: dict) -> tuple[int, int] | None:
    if not isinstance(row, dict):
        raise ValueError("malformed repository artifact metadata")
    match = ARTIFACT_NAME.fullmatch(str(row.get("name", "")))
    if match is None:
        return None
    run_id, attempt = (int(x) for x in match.groups())
    source = row.get("workflow_run")
    if not isinstance(source, dict) or source.get("id") != run_id:
        raise ValueError("artifact name and workflow_run identity conflict")
    if not isinstance(row.get("id"), int) or row["id"] <= 0:
        raise ValueError("invalid repository artifact identity")
    if not isinstance(row.get("size_in_bytes"), int) or row["size_in_bytes"] < 0:
        raise ValueError("invalid repository artifact size")
    return run_id, attempt


def _trusted_run(run: dict, run_id: int, attempt: int) -> str:
    if (not isinstance(run, dict) or run.get("id") != run_id or
            run.get("path") != WORKFLOW or run.get("name") != "Collect public fire observations"
            or run.get("head_branch") != "main" or
            (run.get("repository") or {}).get("full_name") != REPO or
            run.get("status") != "completed" or run.get("conclusion") != "success" or
            not isinstance(run.get("run_attempt"), int) or
            attempt > run["run_attempt"] or
            not re.fullmatch(r"[a-f0-9]{40}", str(run.get("head_sha", "")))):
        raise ValueError("artifact is not from a successful official collection run")
    return run["head_sha"]


def _extract_agency(payload: bytes, *, run_id: int, head_sha: str,
                    run_started_at: str, artifact_created_at: str) -> tuple[str, bytes] | None:
    if not isinstance(payload, bytes) or len(payload) > MAX_DOWNLOAD:
        raise ValueError("oversized or invalid GitHub Actions artifact ZIP")
    seen = set()
    candidates = []
    with zipfile.ZipFile(BytesIO(payload)) as bundle:
        infos = bundle.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError("too many members in original artifact")
        for info in infos:
            name = info.filename
            pieces = PurePosixPath(name).parts
            if (name in seen or not pieces or name.startswith("/") or
                    "\\" in name or any(part in ("..", ".") for part in pieces)
                    or stat.S_ISLNK(info.external_attr >> 16)):
                raise ValueError("unsafe or duplicate file in Actions artifact")
            seen.add(name)
            if not RECEIPT_NAME.fullmatch(name):
                continue
            if info.is_dir() or info.file_size > MAX_COMPRESSED_BYTES or info.file_size < 1:
                raise ValueError("agency source member has invalid size or type")
            candidates.append(info)
        if len(candidates) > 1:
            raise ValueError("more than one original agency receipt in one collection artifact")
        if not candidates:
            return None  # Pixel-only artifacts remain outside this source vault.
        item = candidates[0]
        raw = bundle.read(item)
    with tempfile.TemporaryDirectory(prefix="agency-zip-validate-") as folder:
        path = Path(folder) / item.filename
        path.write_bytes(raw)
        receipt = _read(path)
    if (receipt.get("run_id") != str(run_id) or receipt.get("head_sha") != head_sha):
        raise ValueError("original receipt does not belong to the verified Actions run")
    captured = _time(receipt["captured_at"])
    started, created = _time(run_started_at), _time(artifact_created_at)
    if not started - timedelta(minutes=5) <= captured <= created + timedelta(minutes=5):
        raise ValueError("original receipt time is inconsistent with Actions run")
    return item.filename, raw



PROGRESS_FILE = ".actions-sync-state.json"
MAX_PROGRESS_ENTRIES = 20000


def _read_progress(vault: Path) -> dict:
    path = vault / PROGRESS_FILE
    if not path.exists() and not path.is_symlink():
        return {}
    if (path.is_symlink() or not path.is_file() or
            path.stat().st_size > 2 * 1024 * 1024):
        raise ValueError("unsafe private Actions sync progress file")
    document = json.loads(path.read_text(encoding="utf-8"))
    rows = document.get("checked") if isinstance(document, dict) else None
    if document.get("schema_version") != 1 or not isinstance(rows, dict) or len(rows)>MAX_PROGRESS_ENTRIES:
        raise ValueError("invalid local Actions sync progress format")
    for key, value in rows.items():
        if (not re.fullmatch(r"[1-9]\\d*",key) or not isinstance(value,dict) or
                not isinstance(value.get("run_id"),int) or value["run_id"] <= 0 or
                not isinstance(value.get("attempt"),int) or value["attempt"] <= 0 or
                value.get("kind") not in ("agency","pixel_only") or
                (value["kind"]=="agency" and
                 (not RECEIPT_NAME.fullmatch(str(value.get("receipt_name",""))) or
                  not re.fullmatch(r"[a-f0-9]{64}",str(value.get("receipt_sha256","")))))):
            raise ValueError("invalid source archive progress record")
    return rows


def _atomic_progress(vault: Path, rows: dict) -> None:
    if len(rows) > MAX_PROGRESS_ENTRIES:
        raise ValueError("Actions progress capacity exceeded")
    _prepare(vault,create=True)
    fd, temporary = tempfile.mkstemp(prefix=".actions-sync-",suffix=".tmp",dir=vault)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump({"schema_version":1,"checked":rows},stream,sort_keys=True,
                      ensure_ascii=False,separators=(",",":"))
            stream.write("\\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,vault/PROGRESS_FILE)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _is_checked(vault: Path, progress: dict, artifact: dict,
                run_id: int, attempt: int) -> bool:
    item=progress.get(str(artifact["id"]))
    if item is None:
        return False
    if item["run_id"] != run_id or item["attempt"] != attempt:
        raise ValueError("GitHub Actions artifact conflicts with saved local progress")
    if item["kind"] == "pixel_only":
        return True  # Artifact IDs are immutable; no agency source was present.
    path=vault/"receipts"/item["receipt_name"]
    if not path.is_file() or path.is_symlink():
        return False  # Recover the removed original if the Actions artifact still exists.
    original=_scan(path)
    if original["sha256"] != item["receipt_sha256"]:
        raise ValueError("archived original changed since Actions progress")
    return True


def sync(vault: Path, client, *, pages: int = 5, max_downloads: int = 32,
         since: str | None = None, dry_run: bool = False) -> dict:
    """Idempotent bounded pull: classify expiry/incomplete discovery explicitly."""
    vault = _private_path(Path(vault))
    if not 1 <= pages <= 30 or not 1 <= max_downloads <= 200:
        raise ValueError("pages or maximum artifact downloads outside bounded limits")
    cutoff = _time(since) if since else None
    if vault.exists() and not (vault / "receipts").is_dir():
        raise ValueError("existing destination is not a private receipt vault")
    selected = []
    progress = _read_progress(vault) if vault.exists() else {}
    cached = 0
    listed = 0
    page_exhausted = False
    known = set()
    expired = 0
    for page in range(1, pages + 1):
        response = client.list_artifacts(page)
        artifacts = response.get("artifacts")
        if not isinstance(artifacts, list) or len(artifacts) > PER_PAGE:
            raise ValueError("invalid GitHub artifact listing")
        for row in artifacts:
            listed += 1
            identity = _artifact(row)
            if identity is None:
                continue
            if row["id"] in known:
                raise ValueError("duplicate GitHub Actions artifact across pages")
            known.add(row["id"])
            if row.get("expired") is True:
                expired += 1
                continue
            if row.get("expired") is not False:
                raise ValueError("unknown original artifact expiry")
            if cutoff and _time(row["created_at"]) < cutoff:
                continue
            if row["size_in_bytes"] > MAX_DOWNLOAD:
                raise ValueError("original collection artifact ZIP exceeds 100 MiB")
            if _is_checked(vault,progress,row,*identity):
                cached += 1
            else:
                selected.append((row, *identity))
        if len(artifacts) < PER_PAGE:
            page_exhausted = True
            break
    selected.sort(key=lambda item: (item[0]["created_at"], item[0]["id"]), reverse=True)
    omitted = max(0, len(selected) - max_downloads)
    selected = selected[:max_downloads]
    result = {
        "schema_version": 1,
        "source": "github_actions_official_collection_artifacts",
        "discovered_artifacts": listed,
        "candidate_archives": len(selected) + omitted + cached,
        "already_checked_archives": cached,
        "selected_archives": len(selected),
        "expired_candidates": expired,
        "outside_download_limit": omitted,
        "listing_page_cap_reached": not page_exhausted,
        "discovery_exhaustive": page_exhausted and omitted == 0 and cutoff is None,
        "since": _timestamp(since) if since else None,
        "dry_run": bool(dry_run),
        "downloaded_archives": 0,
        "pixel_only_or_no_agency_receipt": 0,
        "new_original_agency_receipts": 0,
        "existing_original_agency_receipts": 0,
        "verified_fire_outcomes": 0,
        "warning": "A missing/expired Actions artifact is an evidence gap, never proof of no fire.",
    }
    if dry_run:
        return result
    # Each artifact commits independently; interruptions are harmless to existing originals.
    # Do not create an empty vault if no original agency evidence is available.
    for artifact, run_id, attempt in selected:
        run = client.get_run(run_id)
        head_sha = _trusted_run(run, run_id, attempt)
        archive = client.download_zip(artifact["id"])
        result["downloaded_archives"] += 1
        candidate = _extract_agency(archive, run_id=run_id, head_sha=head_sha,
            run_started_at=run["run_started_at"],
            artifact_created_at=artifact["created_at"])
        if candidate is None:
            result["pixel_only_or_no_agency_receipt"] += 1
            _atomic_progress(vault, {**progress, str(artifact["id"]): {
                "run_id":run_id,"attempt":attempt,"kind":"pixel_only"}})
            progress[str(artifact["id"])] = {
                "run_id":run_id,"attempt":attempt,"kind":"pixel_only"}
            continue
        name, raw = candidate
        with tempfile.TemporaryDirectory(prefix="agency-original-") as folder:
            temp = Path(folder) / name
            temp.write_bytes(raw)
            added = ingest(vault, Path(folder))
        result["new_original_agency_receipts"] += added["new_original_receipts"]
        result["existing_original_agency_receipts"] += added["already_present"]
        progress[str(artifact["id"])] = {"run_id":run_id,"attempt":attempt,
            "kind":"agency","receipt_name":name,
            "receipt_sha256":hashlib.sha256(raw).hexdigest()}
        _atomic_progress(vault, progress)
    if vault.exists() and _inventory(vault/"receipts",allow_empty=True):
        state = verify(vault)
        result["vault_receipts"] = state["manifest"]["file_count"]
        result["vault_manifest_sha256"] = state["manifest_sha256"]
        result["scan_gaps_over_9h"] = len(state["source_health"]["gaps_over_9_hours"])
    else:
        result["vault_receipts"] = 0
        result["vault_manifest_sha256"] = None
        result["scan_gaps_over_9h"] = None
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Pull genuine expiring official-collector Actions receipts into private local vault")
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--pages", type=int, default=5)
    parser.add_argument("--max-downloads", type=int, default=32)
    parser.add_argument("--since", help="UTC-aware minimum artifact creation time")
    parser.add_argument("--dry-run", action="store_true",
                        help="Inspect metadata without downloading or modifying local files")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("set GH_TOKEN or GITHUB_TOKEN with Actions:read; no token is printed")
    result = sync(args.vault, GitHubArtifacts(token), pages=args.pages,
                  max_downloads=args.max_downloads, since=args.since,
                  dry_run=args.dry_run)
    print(json.dumps(result,sort_keys=True))


if __name__ == "__main__":
    main()
