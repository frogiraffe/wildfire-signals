"""Publish immutable, dated public research evidence in GitHub Releases."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO = "frogiraffe/wildfire-signals"
MAX_ASSET_BYTES = 100 * 1024 * 1024
ASSET_NAME = re.compile(r"(?:firms-pixels-[\w-]+\.jsonl\.gz|"
                        r"firms-pixel-scan-[\w-]+\.json\.gz)\Z")


def github_request(method, url, data=None, content_type=None):
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN required for release publication")
    if not url.startswith(("https://api.github.com/", "https://uploads.github.com/")):
        raise ValueError("unexpected GitHub API URL")
    headers = {"Authorization":f"Bearer {token}",
               "Accept":"application/vnd.github+json",
               "X-GitHub-Api-Version":"2022-11-28"}
    if content_type:
        headers["Content-Type"] = content_type
    try:
        with urlopen(Request(url,data=data,method=method,headers=headers),timeout=90) as response:
            return json.load(response)
    except HTTPError as exc:
        if method == "GET" and exc.code == 404:
            return None
        raise


def publish_daily_release(directory: Path, repo: str, sha: str, *, api=github_request) -> dict:
    if repo != REPO or not re.fullmatch(r"[a-f0-9]{40}",sha):
        raise ValueError("unexpected repository or commit")
    directory = Path(directory)
    scans = list(directory.glob("firms-pixel-scan-*.json.gz"))
    if len(scans) != 1:
        raise ValueError("exactly one pixel scan receipt required")
    with gzip.open(scans[0],"rb") as source:
        scan = json.load(source)
    if scan.get("schema_version") != 1 or scan.get("role") != "firms_pixel_scan_receipt":
        raise ValueError("invalid pixel scan receipt")
    at = datetime.fromisoformat(scan["scan_at"])
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("scan time requires UTC offset")
    date = at.astimezone(timezone.utc).date().isoformat()
    if set(scan.get("source_states",{})) != {"VIIRS_NOAA20_NRT","VIIRS_NOAA21_NRT"}:
        raise ValueError("incomplete FIRMS source states")
    files = sorted(path for path in directory.iterdir()
                   if path.name.startswith("firms-")
                   and path.name.endswith((".json.gz",".jsonl.gz")))
    expected_pixels = {row["name"]:row["sha256"] for row in scan.get("pixel_files",[])}
    pixels = {path.name for path in files if path.name.startswith("firms-pixels-")}
    if pixels != set(expected_pixels):
        raise ValueError("pixel files differ from scan receipt")
    for path in files:
        if (path.is_symlink() or not path.is_file() or not ASSET_NAME.fullmatch(path.name)
                or path.stat().st_size > MAX_ASSET_BYTES):
            raise ValueError("invalid research asset")
        if path.name in expected_pixels and hashlib.sha256(path.read_bytes()).hexdigest() != expected_pixels[path.name]:
            raise ValueError("pixel asset digest mismatch")
    tag = f"analysis-evidence-{date}"
    base = f"https://api.github.com/repos/{repo}/releases"
    release = api("GET",f"{base}/tags/{tag}")
    created = release is None
    if created:
        body = {"tag_name":tag,"target_commitish":sha,"name":f"Research evidence {date}",
                "body":"Dated NASA FIRMS source receipts and thermal detections; "
                       "not verified fires or forecasts. See asset scan receipt for source status.",
                "draft":True,"prerelease":True,"make_latest":"false"}
        release = api("POST",base,json.dumps(body).encode(),"application/json")
    existing = {item["name"]:item for item in release.get("assets",[])}
    uploaded = 0
    for path in files:
        content = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if path.name in existing:
            if existing[path.name].get("digest") != digest:
                raise ValueError(f"release asset digest conflict: {path.name}")
            continue
        upload_base = release["upload_url"].split("{",1)[0]
        uploaded_asset = api("POST",f"{upload_base}?name={quote(path.name)}",
                             content,"application/octet-stream")
        if uploaded_asset.get("digest") != digest:
            raise ValueError(f"uploaded asset digest mismatch: {path.name}")
        uploaded += 1
    if release.get("draft"):
        api("PATCH",f"{base}/{release['id']}",
            json.dumps({"draft":False}).encode(),"application/json")
    return {"tag":tag,"uploaded":uploaded,"assets":len(files),"created":created}


def main():
    result = publish_daily_release(Path(os.environ["ANALYSIS_RECEIPT_DIR"]),
                                   os.environ["GITHUB_REPOSITORY"],os.environ["GITHUB_SHA"])
    print(json.dumps(result,sort_keys=True))


if __name__ == "__main__":
    main()
