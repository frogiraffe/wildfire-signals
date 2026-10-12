"""Bounded, resumable GitHub Release research-asset synchronization.

Only canonical public GitHub Releases from this project can be downloaded.
Every daily scan is staged, cross-verified, then atomically installed locally.
No live collection, Cloudflare changes or paid resources are involved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

from .pixel_history import (
    MAX_SCAN_JSON, PIXEL_NAME, SCAN_NAME, _validated_scan,
    coverage_report, import_release_assets,
)
from .release_archive import MAX_ASSET_BYTES, REPO

TAG = re.compile(r"analysis-evidence-(\d{4}-\d{2}-\d{2})\Z")
DIGEST = re.compile(r"sha256:([0-9a-f]{64})\Z")
MAX_RELEASES = 30
MAX_PAGES = 5
MAX_TOTAL_BYTES = 512 * 1024 * 1024
ALLOWED_REDIRECT_HOSTS = frozenset({
    "github.com", "release-assets.githubusercontent.com",
    "objects.githubusercontent.com", "github-releases.githubusercontent.com",
})


class _TrustedRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urlsplit(newurl)
        if parts.scheme != "https" or parts.hostname not in ALLOWED_REDIRECT_HOSTS:
            raise ValueError("untrusted GitHub release asset redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _asset_url(tag: str, asset: dict) -> str:
    name = asset["name"]
    url = asset["browser_download_url"]
    exact = f"https://github.com/{REPO}/releases/download/{quote(tag)}/{quote(name)}"
    if url != exact:
        raise ValueError(f"release asset URL is not canonical: {name}")
    return url


def _get_releases(page: int) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "WildfireSignals-ResearchSync/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"https://api.github.com/repos/{REPO}/releases?per_page=100&page={page}"
    with urlopen(Request(url, headers=headers), timeout=25) as response:
        raw = response.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("GitHub release metadata response exceeds limit")
    rows = json.loads(raw)
    if not isinstance(rows, list):
        raise ValueError("unexpected GitHub release listing")
    return rows


def _download(url: str, target: Path, max_size: int) -> str:
    """Stream without unbounded memory, enforce redirect hosts and digest later."""
    opener = build_opener(_TrustedRedirect())
    digest = hashlib.sha256()
    total = 0
    request = Request(url, headers={"User-Agent": "WildfireSignals-ResearchSync/1"})
    with opener.open(request, timeout=60) as response, target.open("xb") as output:
        while True:
            block = response.read(min(256 * 1024, max_size - total + 1))
            if not block:
                break
            total += len(block)
            if total > max_size:
                raise ValueError("downloaded asset exceeds declared size/budget")
            digest.update(block)
            output.write(block)
    if total != max_size:
        raise ValueError("release asset size does not match metadata")
    return digest.hexdigest()


def _plan_one(row: dict) -> dict | None:
    tag = row.get("tag_name")
    match = TAG.fullmatch(tag) if isinstance(tag, str) else None
    if not match or row.get("draft") or row.get("prerelease") is not True:
        return None
    try:
        date.fromisoformat(match.group(1))
    except ValueError:
        raise ValueError(f"invalid research release date: {tag}") from None
    assets = row.get("assets")
    if not isinstance(assets, list) or len(assets) > 3:
        raise ValueError("research release must contain 1 scan and up to 2 pixel assets")
    names = set()
    checks = []
    scan = None
    for asset in assets:
        if not isinstance(asset, dict):
            raise ValueError("invalid release asset")
        name = asset.get("name")
        if not isinstance(name, str) or name in names:
            raise ValueError("duplicate or invalid release asset name")
        names.add(name)
        scan_match = SCAN_NAME.fullmatch(name)
        pixel_match = PIXEL_NAME.fullmatch(name)
        if not scan_match and not pixel_match:
            raise ValueError(f"unexpected research release asset: {name}")
        digest = DIGEST.fullmatch(asset.get("digest") or "")
        size = asset.get("size")
        if not digest or type(size) is not int or not 0 < size <= MAX_ASSET_BYTES:
            raise ValueError(f"missing SHA-256 or invalid release asset size: {name}")
        if digest.group(1)[:16] != (scan_match or pixel_match).group(2):
            raise ValueError("release asset filename and digest mismatch")
        _asset_url(tag, asset)
        checks.append({"name":name,"url":asset["browser_download_url"],
                       "sha256":digest.group(1),"size":size})
        if scan_match:
            if scan:
                raise ValueError("multiple research scan receipts in one daily release")
            scan = name
            if not scan_match.group(1).startswith(match.group(1).replace("-", "")):
                raise ValueError("daily release tag and scan stamp disagree")
    if scan is None:
        raise ValueError("missing research scan receipt")
    stamp = SCAN_NAME.fullmatch(scan).group(1)
    if any(PIXEL_NAME.fullmatch(x["name"]) and
           PIXEL_NAME.fullmatch(x["name"]).group(1) != stamp for x in checks):
        raise ValueError("mixed scan times in research release")
    return {"tag":tag, "assets":sorted(checks,key=lambda x:x["name"]),
            "bytes":sum(x["size"] for x in checks),"scan_name":scan}


def discover(*, since: str | None = None, max_releases: int = 8,
             list_page=_get_releases) -> list[dict]:
    if type(max_releases) is not int or not 1 <= max_releases <= MAX_RELEASES:
        raise ValueError(f"max_releases must be 1..{MAX_RELEASES}")
    if since is not None:
        date.fromisoformat(since)
    selected = {}
    for page in range(1, MAX_PAGES + 1):
        rows = list_page(page)
        if not rows:
            break
        for row in rows:
            tag = row.get("tag_name","")
            if isinstance(tag,str) and TAG.fullmatch(tag) and (
                    since is None or tag[-10:] >= since):
                plan = _plan_one(row)
                if plan:
                    if plan["tag"] in selected:
                        raise ValueError("duplicate research release tag")
                    selected[plan["tag"]] = plan
        if len(selected) >= max_releases or len(rows) < 100:
            break
    # Select the latest N dates, then ingest that bounded set oldest-first.
    # Otherwise a long first API page would accidentally select older releases.
    newest = sorted(selected.values(),key=lambda p:p["tag"],reverse=True)[:max_releases]
    return sorted(newest,key=lambda p:p["tag"])


def sync_releases(destination: str | Path, *, since: str | None = None,
                  max_releases: int = 8, max_total_bytes: int = MAX_TOTAL_BYTES,
                  list_page=_get_releases, download=_download) -> dict:
    if type(max_total_bytes) is not int or not 1 <= max_total_bytes <= MAX_TOTAL_BYTES:
        raise ValueError("invalid total download budget")
    plan = discover(since=since,max_releases=max_releases,list_page=list_page)
    if sum(p["bytes"] for p in plan) > max_total_bytes:
        raise ValueError("selected research releases exceed download budget")
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError("download directory cannot be a symlink")
    destination.mkdir(parents=True,exist_ok=True)
    downloaded = skipped = total_bytes = 0
    for release in plan:
        final = destination / release["tag"]
        if final.is_symlink():
            raise ValueError("local release directory cannot be a symlink")
        if final.exists():
            if not final.is_dir():
                raise ValueError("release destination is not a directory")
            present = {p.name for p in final.iterdir()}
            required = {p["name"] for p in release["assets"]}
            if present != required:
                raise ValueError(f"incomplete or unexpected existing release: {release['tag']}")
            for asset in release["assets"]:
                path = final/asset["name"]
                if (path.is_symlink() or not path.is_file()
                    or path.stat().st_size != asset["size"]
                    or hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]):
                    raise ValueError(f"existing release asset hash conflict: {asset['name']}")
            receipt, _ = _validated_scan(final/release["scan_name"])
            declared = {x["name"]:x["sha256"] for x in receipt["pixel_files"]}
            actual = {x["name"]:x["sha256"] for x in release["assets"]
                      if x["name"] != release["scan_name"]}
            if declared != actual:
                raise ValueError("existing release differs from scan receipt manifest")
            skipped += 1
            continue
        stage = Path(tempfile.mkdtemp(prefix=".wildfire-sync-",dir=destination))
        try:
            for asset in release["assets"]:
                written_digest = download(asset["url"],stage/asset["name"],asset["size"])
                if written_digest != asset["sha256"]:
                    raise ValueError(f"downloaded asset SHA-256 mismatch: {asset['name']}")
                total_bytes += asset["size"]
            receipt, _ = _validated_scan(stage/release["scan_name"])
            declared = {x["name"]:x["sha256"] for x in receipt["pixel_files"]}
            actual = {x["name"]:x["sha256"] for x in release["assets"]
                      if x["name"] != release["scan_name"]}
            if declared != actual:
                raise ValueError("release assets do not match scan receipt manifest")
            # Single per-release atomic directory transition: no partial imported scans.
            if final.exists():
                raise ValueError("release destination appeared during download")
            stage.rename(final)
            downloaded += 1
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return {"schema_version":1,"discovered_releases":len(plan),
            "downloaded_releases":downloaded,"skipped_verified_releases":skipped,
            "downloaded_compressed_bytes":total_bytes,
            "archive_dir":str(destination),
            "role":"research thermal pixels, not verified wildfire incidents",
            "note":"No eligible releases means no downloaded archive, not no wildfires."}


def main():
    parser=argparse.ArgumentParser(description="Sync, verify and index GitHub FIRMS research Releases")
    parser.add_argument("--assets-dir",required=True,type=Path)
    parser.add_argument("--db",required=True,type=Path)
    parser.add_argument("--since",help="Earliest daily research release date (YYYY-MM-DD)")
    parser.add_argument("--max-releases",type=int,default=8)
    parser.add_argument("--max-total-mb",type=int,default=256)
    parser.add_argument("--at",help="Historical decision timestamp UTC; default now")
    parser.add_argument("--hours",type=int,default=72)
    parser.add_argument("--latitude",type=float)
    parser.add_argument("--longitude",type=float)
    parser.add_argument("--radius-km",type=float)
    parser.add_argument("--coverage-json",type=Path)
    args=parser.parse_args()
    if (args.assets_dir.resolve()==args.db.resolve() or
            args.db.resolve().is_relative_to(args.assets_dir.resolve())):
        parser.error("SQLite DB must live outside the downloaded release asset tree")
    if args.coverage_json and args.coverage_json.resolve() in {
        args.db.resolve(),args.assets_dir.resolve()}:
        parser.error("coverage report cannot overwrite the source archive")
    if args.coverage_json and args.coverage_json.exists():
        parser.error("coverage output exists; refusing overwrite")
    sync=sync_releases(args.assets_dir,since=args.since,max_releases=args.max_releases,
                       max_total_bytes=args.max_total_mb*1024*1024)
    imported=(import_release_assets(args.db,args.assets_dir) if
              sync["discovered_releases"] else None)
    timestamp=args.at or datetime.now(timezone.utc).isoformat()
    coverage=(coverage_report(args.db,at=timestamp,hours=args.hours,
             latitude=args.latitude,longitude=args.longitude,
             radius_km=args.radius_km) if imported is not None else None)
    output={"sync":sync,"import":imported,"coverage":coverage}
    if args.coverage_json:
        args.coverage_json.parent.mkdir(parents=True,exist_ok=True)
        with args.coverage_json.open("x",encoding="utf-8") as f:
            json.dump(output,f,indent=2,sort_keys=True)
            f.write("\n")
    print(json.dumps(output,sort_keys=True))


if __name__=="__main__":
    main()
