"""Bounded NWS forecast receipt pilot; it does not publish or predict fire."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .history import HistoryStore

NWS_RIGHTS = "https://www.weather.gov/documentation/services-web-api"
GRID_URL = re.compile(r"https://api\.weather\.gov/gridpoints/([A-Z]{3}/\d+,\d+)$")
SHA256 = re.compile(r"[a-f0-9]{64}$")
MAX_RAW_BYTES = 1_000_000
FIELDS = {
    "windSpeed": ("wmoUnit:km_h-1", lambda v: v >= 0),
    "windDirection": ("wmoUnit:degree_(angle)", lambda v: 0 <= v <= 360),
    "windGust": ("wmoUnit:km_h-1", lambda v: v >= 0),
    "temperature": ("wmoUnit:degC", lambda v: -100 <= v <= 70),
    "relativeHumidity": ("wmoUnit:percent", lambda v: 0 <= v <= 100),
    "quantitativePrecipitation": ("wmoUnit:mm", lambda v: v >= 0),
}


def _aware(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("invalid NWS timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("NWS timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _valid_interval(value: str) -> tuple[datetime, datetime]:
    if not isinstance(value, str) or "/" not in value:
        raise ValueError("invalid NWS validTime interval")
    start, duration = value.split("/", 1)
    beginning = _aware(start)
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", duration)
    seconds = sum(int(part or 0) * factor for part, factor in
                  zip(match.groups(), (86400, 3600, 60, 1))) if match else 0
    if not 0 < seconds <= 8 * 86400:
        raise ValueError("invalid NWS validTime duration")
    return beginning, beginning + timedelta(seconds=seconds)


def nws_grid_record(grid: dict, *, latitude: float, longitude: float,
                    grid_url: str, captured_at: str, raw_sha256: str) -> dict:
    match = GRID_URL.fullmatch(grid_url)
    if not match or not SHA256.fullmatch(raw_sha256):
        raise ValueError("invalid NWS grid provenance")
    if (not math.isfinite(latitude) or not math.isfinite(longitude) or
            not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        raise ValueError("invalid NWS point")
    p = grid.get("properties") if isinstance(grid, dict) else None
    if not isinstance(p, dict):
        raise ValueError("NWS grid properties unavailable")
    update = _aware(p.get("updateTime"))
    received = _aware(captured_at)
    if update > received:
        raise ValueError("forecast update cannot postdate receipt")
    _valid_interval(p.get("validTimes"))
    fields = {}
    for name, (unit, valid) in FIELDS.items():
        field = p.get(name)
        if not isinstance(field, dict) or field.get("uom") != unit or not isinstance(field.get("values"), list):
            raise ValueError(f"NWS {name} field or unit unavailable")
        if len(field["values"]) > 1000:
            raise ValueError("NWS field exceeds pilot limit")
        for row in field["values"]:
            if not isinstance(row, dict):
                raise ValueError("invalid NWS field row")
            _valid_interval(row.get("validTime"))
            value = row.get("value")
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or
                    not math.isfinite(value) or not valid(value)):
                raise ValueError("invalid NWS weather value")
        fields[name] = {"uom": unit, "values": field["values"]}
    return {"subject_kind": "weather_forecast_snapshot", "provider": "nws_grid",
            "source_id": match.group(1), "record_type": "grid_forecast",
            "observed_at": update.isoformat(), "captured_at": received.isoformat(),
            "source_url": grid_url, "rights_url": NWS_RIGHTS,
            "payload": {"point": {"latitude": latitude, "longitude": longitude},
                        "source_update_at": p["updateTime"],
                        "source_valid_times": p["validTimes"],
                        "grid_response_sha256": raw_sha256,
                        "fields": fields,
                        "evidence_role": "captured_forecast_not_observation"}}


def _fetch_json(url: str) -> tuple[dict, bytes]:
    if not (re.fullmatch(r"https://api\.weather\.gov/points/-?\d+\.\d+,-?\d+\.\d+", url)
            or GRID_URL.fullmatch(url)):
        raise ValueError("invalid NWS request URL")
    request = Request(url, headers={
        "User-Agent": "WildfireSignals/0.1 (https://github.com/frogiraffe/wildfire-signals)",
        "Accept": "application/geo+json"})
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, msg, headers, newurl):
            raise ValueError("NWS redirect rejected")

    with build_opener(NoRedirect()).open(request, timeout=20) as response:
        raw = response.read(MAX_RAW_BYTES + 1)
    if len(raw) > MAX_RAW_BYTES:
        raise ValueError("NWS response exceeds pilot limit")
    return json.loads(raw), raw


def _received_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_raw(raw_dir: Path, raw: bytes) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    (raw_dir / f"{digest}.json.gz").write_bytes(gzip.compress(raw, mtime=0))
    return digest


def _validate_point(point: dict, latitude: float, longitude: float, grid_url: str) -> None:
    match = GRID_URL.fullmatch(grid_url)
    p = point.get("properties") if isinstance(point, dict) else None
    geometry = point.get("geometry") if isinstance(point, dict) else None
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if (not match or not isinstance(p, dict) or not isinstance(coordinates, list)
            or len(coordinates) < 2 or geometry.get("type") != "Point"
            or any(isinstance(v, bool) or not isinstance(v, (int, float))
                   for v in coordinates[:2])
            or abs(coordinates[0] - longitude) > .00011
            or abs(coordinates[1] - latitude) > .00011
            or f'{p.get("gridId")}/{p.get("gridX")},{p.get("gridY")}' != match.group(1)):
        raise ValueError("NWS point/grid location mismatch")


def _commitment(report: dict) -> str:
    return hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def run_pilot(db_path: Path, raw_dir: Path, *, latitude: float, longitude: float) -> dict:
    if db_path.exists() or raw_dir.exists():
        raise FileExistsError("weather pilot output already exists")
    if (isinstance(latitude, bool) or isinstance(longitude, bool) or
            not all(math.isfinite(v) for v in (latitude, longitude)) or
            not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
        raise ValueError("invalid NWS point")
    started_at = _received_at()
    point_url = f"https://api.weather.gov/points/{latitude:.4f},{longitude:.4f}"
    point, point_raw = _fetch_json(point_url)
    point_captured = _received_at()
    point_properties = point.get("properties") if isinstance(point, dict) else None
    grid_url = point_properties.get("forecastGridData") if isinstance(point_properties, dict) else None
    if not isinstance(grid_url, str) or not GRID_URL.fullmatch(grid_url):
        raise ValueError("NWS grid URL unavailable or invalid")
    _validate_point(point, latitude, longitude, grid_url)
    grid, grid_raw = _fetch_json(grid_url)
    grid_captured = _received_at()
    grid_hash = hashlib.sha256(grid_raw).hexdigest()
    record = nws_grid_record(grid, latitude=latitude, longitude=longitude,
                             grid_url=grid_url, captured_at=grid_captured,
                             raw_sha256=grid_hash)
    raw_dir.parent.mkdir(parents=True, exist_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    stage_raw = Path(tempfile.mkdtemp(prefix=".weather-raw-", dir=raw_dir.parent))
    stage_db_dir = Path(tempfile.mkdtemp(prefix=".weather-db-", dir=db_path.parent))
    stage_db = stage_db_dir / "weather.sqlite3"
    published_raw = False
    try:
        point_hash = _write_raw(stage_raw, point_raw)
        _write_raw(stage_raw, grid_raw)
        store = HistoryStore(stage_db)
        try:
            observation_id = store.append(record)
        finally:
            store.close()
        report = {"schema_version": 1, "started_at": started_at,
                  "point_url": point_url, "point_captured_at": point_captured,
                  "point_sha256": point_hash, "point_bytes": len(point_raw),
                  "grid_url": grid_url, "grid_captured_at": grid_captured,
                  "grid_sha256": grid_hash, "grid_bytes": len(grid_raw),
                  "latitude": latitude, "longitude": longitude,
                  "observation_id": observation_id, "sqlite_bytes": stage_db.stat().st_size,
                  "compressed_raw_bytes": sum(p.stat().st_size for p in stage_raw.glob("*.json.gz")),
                  "predictive_evidence": False}
        report["manifest_sha256"] = _commitment(report)
        (stage_raw / "weather-manifest.json").write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        if db_path.exists() or raw_dir.exists():
            raise FileExistsError("weather pilot output already exists")
        stage_raw.rename(raw_dir)
        published_raw = True
        stage_db.rename(db_path)
        return report
    except Exception:
        if published_raw:
            shutil.rmtree(raw_dir)
        raise
    finally:
        shutil.rmtree(stage_raw, ignore_errors=True)
        shutil.rmtree(stage_db_dir, ignore_errors=True)


def _read_raw(raw_dir: Path, digest: str) -> tuple[dict, bytes]:
    if not SHA256.fullmatch(digest):
        raise ValueError("invalid weather source checksum")
    with gzip.open(raw_dir / f"{digest}.json.gz", "rb") as source:
        raw = source.read(MAX_RAW_BYTES + 1)
    if len(raw) > MAX_RAW_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("weather source checksum mismatch")
    return json.loads(raw), raw


def replay_pilot(raw_dir: Path, db_path: Path) -> dict:
    if db_path.exists():
        raise FileExistsError("replay database already exists")
    manifest = json.loads((raw_dir / "weather-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("unsupported weather manifest")
    receipt_hash = manifest.pop("manifest_sha256", None)
    if not isinstance(receipt_hash, str) or _commitment(manifest) != receipt_hash:
        raise ValueError("weather manifest commitment mismatch")
    point, point_raw = _read_raw(raw_dir, manifest["point_sha256"])
    grid, grid_raw = _read_raw(raw_dir, manifest["grid_sha256"])
    if len(point_raw) != manifest["point_bytes"] or len(grid_raw) != manifest["grid_bytes"]:
        raise ValueError("weather source byte count mismatch")
    if not (_aware(manifest["started_at"]) <= _aware(manifest["point_captured_at"])
            <= _aware(manifest["grid_captured_at"])):
        raise ValueError("weather receipt ordering invalid")
    if manifest["point_url"] != (f'https://api.weather.gov/points/'
                                  f'{manifest["latitude"]:.4f},{manifest["longitude"]:.4f}'):
        raise ValueError("weather point URL mismatch")
    point_properties = point.get("properties") if isinstance(point, dict) else None
    grid_url = point_properties.get("forecastGridData") if isinstance(point_properties, dict) else None
    if grid_url != manifest["grid_url"]:
        raise ValueError("weather point/grid mismatch")
    _validate_point(point, manifest["latitude"], manifest["longitude"], grid_url)
    record = nws_grid_record(grid, latitude=manifest["latitude"],
        longitude=manifest["longitude"], grid_url=grid_url,
        captured_at=manifest["grid_captured_at"], raw_sha256=manifest["grid_sha256"])
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".weather-replay-", dir=db_path.parent) as temp:
        stage_db = Path(temp) / "replay.sqlite3"
        store = HistoryStore(stage_db)
        try:
            observation_id = store.append(record)
        finally:
            store.close()
        if observation_id != manifest["observation_id"]:
            raise ValueError("weather observation identity mismatch")
        if db_path.exists():
            raise FileExistsError("replay database already exists")
        size = stage_db.stat().st_size
        stage_db.rename(db_path)
    return {"restored_records": 1, "sqlite_bytes": size}


def main() -> None:
    parser = argparse.ArgumentParser(description="Bounded local NWS forecast receipt pilot")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    if args.replay:
        result = replay_pilot(args.raw_dir, args.db)
    else:
        if args.latitude is None or args.longitude is None:
            parser.error("--latitude and --longitude are required unless --replay")
        result = run_pilot(args.db, args.raw_dir,
                           latitude=args.latitude, longitude=args.longitude)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
