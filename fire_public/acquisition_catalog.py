"""Bounded NASA CMR VIIRS granule catalog audit for an offline FIRMS study.

CMR metadata describes a six-minute geolocation product and its search footprint.
It does not establish cell-level acquisition, cloud-free viewing, a complete active
fire product, or a no-detection observation. Never turn its gaps into negatives.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .historical_rollup import _bytes, _study
from .historical_signal_analysis import _read_only

CMR = "https://cmr.earthdata.nasa.gov/search/granules.json"
PRODUCTS = {"VIIRS_NOAA20_NRT": "VJ103IMG_NRT",
            "VIIRS_NOAA21_NRT": "VJ203IMG_NRT"}
ACTIVE_PRODUCTS = {"VIIRS_NOAA20_NRT": "VJ114IMG_NRT",
                   "VIIRS_NOAA21_NRT": "VJ214IMG_NRT"}
VERSION = "2.1"
ACTIVE_VERSION = "2"
PAGE_SIZE = 100
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _window(start_date: str, end_date: str) -> tuple[date, date]:
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    if end < start or (end - start).days > 6:
        raise ValueError("CMR pilot query must cover 1..7 UTC dates")
    return start, end


def _bbox(value: str) -> str:
    parts = value.split(",")
    if len(parts) != 4:
        raise ValueError("bounding box must be west,south,east,north")
    try:
        west, south, east, north = map(float, parts)
    except ValueError:
        raise ValueError("invalid CMR bounding box") from None
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ValueError("invalid CMR bounding box; split antimeridian queries")
    return value


def catalog_url(product: str, start_date: str, end_date: str, bbox: str) -> str:
    if product in PRODUCTS.values():
        version = VERSION
    elif product in ACTIVE_PRODUCTS.values():
        version = ACTIVE_VERSION
    else:
        raise ValueError("unsupported NOAA-20/21 imagery or active-fire product")
    start, end = _window(start_date, end_date)
    params = {"short_name": product, "version": version,
              "temporal": f"{start}T00:00:00Z,{end + timedelta(days=1)}T00:00:00Z",
              "bounding_box": _bbox(bbox), "page_size": str(PAGE_SIZE)}
    return CMR + "?" + urlencode(params)


def fetch_catalog_snapshot(*, start_date: str, end_date: str, bbox: str) -> dict:
    """Capture exact public CMR response bytes; refuse truncated query results."""
    return _fetch_snapshot(PRODUCTS, start_date, end_date, bbox)


def fetch_active_snapshot(*, start_date: str, end_date: str, bbox: str) -> dict:
    """Capture the companion L2 active-fire *catalog*, never its pixel contents."""
    return _fetch_snapshot(ACTIVE_PRODUCTS, start_date, end_date, bbox)


def _fetch_snapshot(products: dict[str, str], start_date: str, end_date: str,
                    bbox: str) -> dict:
    queries = []
    for product in products.values():
        url = catalog_url(product, start_date, end_date, bbox)
        with urlopen(Request(url, headers={"User-Agent": "WildfireSignals-CMRAudit/1",
                                           "Accept": "application/json"}), timeout=30) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            hits = response.headers.get("CMR-Hits")
        if len(body) > MAX_RESPONSE_BYTES or hits is None:
            raise ValueError("CMR response exceeds budget or lacks hit count")
        try:
            count = int(hits)
        except ValueError:
            raise ValueError("invalid CMR hit count") from None
        if count > PAGE_SIZE:
            raise ValueError("incomplete CMR result; narrow the UTC window or bounding box")
        parsed = json.loads(body)
        if len(parsed.get("feed", {}).get("entry", [])) != count:
            raise ValueError("incomplete CMR response")
        queries.append({"product": product, "url": url, "cmr_hits": count,
                        "response_sha256": hashlib.sha256(body).hexdigest(),
                        "body": body.decode("utf-8")})
    return {"schema_version": 1, "fetched_at": datetime.now(timezone.utc).isoformat(),
            "queries": queries}


def _verified_active_granules(snapshot: dict, *, start_date: str, end_date: str,
                              bbox: str) -> tuple[list[dict], list[dict]]:
    if snapshot.get("schema_version") != 1 or len(snapshot.get("queries", [])) != 2:
        raise ValueError("incomplete active-fire CMR source snapshot")
    start, end = _window(start_date, end_date)
    _utc(snapshot["fetched_at"])
    seen_ids, granules, provenance = set(), [], []
    for query, (provider, product) in zip(snapshot["queries"], ACTIVE_PRODUCTS.items(), strict=True):
        if query.get("product") != product or query.get("url") != catalog_url(product, start_date, end_date, bbox):
            raise ValueError("CMR active-fire source query/product contract differs")
        body = query.get("body")
        if not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != query.get("response_sha256"):
            raise ValueError("CMR active-fire source response SHA-256 differs")
        entries = json.loads(body).get("feed", {}).get("entry", [])
        hits = query.get("cmr_hits")
        if type(hits) is not int or hits < 0 or hits > PAGE_SIZE or hits != len(entries):
            raise ValueError("incomplete CMR active-fire source result")
        provenance.append({"product": product, "collection_version": ACTIVE_VERSION,
                           "query_url": query["url"], "response_sha256": query["response_sha256"],
                           "cmr_hits": hits})
        for entry in entries:
            identifier, name = entry.get("id"), entry.get("producer_granule_id", "")
            if (not isinstance(identifier, str) or identifier in seen_ids or
                not name.startswith(product + ".") or
                not identifier.endswith("-LANCEMODIS") or
                not entry.get("collection_concept_id", "").endswith("-LANCEMODIS")):
                raise ValueError("CMR active-fire granule identity/product invalid")
            seen_ids.add(identifier)
            first, last = _utc(entry["time_start"]), _utc(entry["time_end"])
            if (first >= last or last < datetime.combine(start, datetime.min.time(), timezone.utc)
                or first > datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc)
                or not entry.get("polygons")):
                raise ValueError("CMR active-fire granule interval or footprint invalid")
            granules.append({"id": identifier, "product": product, "provider": provider,
                             "producer_granule_id": name, "collection_concept_id": entry["collection_concept_id"],
                             "start_at": first.isoformat(), "end_at": last.isoformat(),
                             "metadata_updated_at": _utc(entry["updated"]).isoformat(),
                             "search_polygons": entry["polygons"]})
    return sorted(granules, key=lambda row: (row["start_at"], row["provider"], row["id"])), provenance


def build_paired_product_report(geolocation_report: dict, active_snapshot: dict) -> dict:
    """Join two CMR catalogs by platform and exact interval, without inferring exposure.

    A paired catalog entry establishes neither cell coverage nor an inspected L2
    detection array. CMR updated timestamps are revisions, not first availability.
    """
    geo = dict(geolocation_report)
    digest = geo.pop("evidence_sha256", None)
    if (geo.get("schema_version") != 1 or geo.get("status") != "granule_catalog_context_only"
        or geo.get("observation_opportunity_verified") is not False
        or not isinstance(digest, str) or hashlib.sha256(_bytes(geo)).hexdigest() != digest):
        raise ValueError("geolocation report SHA-256 or evidence contract invalid")
    start_date, end_date, bbox = geo["start_date"], geo["end_date"], geo["query_bbox_wgs84"]
    active, provenance = _verified_active_granules(active_snapshot, start_date=start_date,
                                                    end_date=end_date, bbox=bbox)
    geos = geo["granules"]
    if geo["population"]["catalog_granules"] != len(geos):
        raise ValueError("geolocation report population differs")
    def key(row):
        return row["provider"], row["start_at"], row["end_at"]
    by_geo, by_active = {}, {}
    for row in geos:
        if row["provider"] not in PRODUCTS or row["product"] != PRODUCTS[row["provider"]]:
            raise ValueError("geolocation product/provider differs")
        by_geo.setdefault(key(row), []).append(row["id"])
    for row in active:
        by_active.setdefault(key(row), []).append(row["id"])
    intervals = []
    for provider, first, last in sorted(by_geo.keys() | by_active.keys(), key=lambda item: (item[1], item[0])):
        g, a = by_geo.get((provider, first, last), []), by_active.get((provider, first, last), [])
        intervals.append({"provider": provider, "start_at": first, "end_at": last,
                          "geolocation_granule_ids": g, "active_fire_granule_ids": a,
                          "pair_status": "both_catalogued" if g and a else
                          ("geolocation_only" if g else "active_fire_only")})
    minutes = []
    for row in geo["candidate_provider_minutes"]:
        observed = _utc(row["observed_minute"] + ":00+00:00")
        matching = [item for item in intervals if item["provider"] == row["provider"]
                    and _utc(item["start_at"]) <= observed < _utc(item["end_at"])]
        geo_ids = sorted({identifier for item in matching for identifier in item["geolocation_granule_ids"]})
        fire_ids = sorted({identifier for item in matching for identifier in item["active_fire_granule_ids"]})
        if geo_ids != sorted(row["catalog_granule_ids"]):
            raise ValueError("geolocation report candidate-minute join differs")
        minutes.append({"provider": row["provider"], "observed_minute": row["observed_minute"],
                        "raw_pixels": row["raw_pixels"], "geolocation_granule_ids": geo_ids,
                        "active_fire_granule_ids": fire_ids,
                        "pair_status": "both_catalogued" if geo_ids and fire_ids else
                        ("geolocation_only" if geo_ids else "active_fire_only" if fire_ids else
                         "neither_exact_interval")})
    report = {"schema_version": 1, "status": "paired_product_catalog_context_only",
              "region": geo["region"], "study_id": geo["study_id"],
              "start_date": start_date, "end_date": end_date, "query_bbox_wgs84": bbox,
              "geolocation_report_sha256": digest,
              "active_catalog_fetched_at": _utc(active_snapshot["fetched_at"]).isoformat(),
              "active_catalog_first_available_at": None,
              "source_queries": provenance, "product_intervals": intervals,
              "candidate_provider_minutes": minutes,
              "population": {"geolocation_granules": len(geos), "active_fire_granules": len(active),
                             "paired_intervals": sum(row["pair_status"] == "both_catalogued" for row in intervals),
                             "geo_only_intervals": sum(row["pair_status"] == "geolocation_only" for row in intervals),
                             "active_only_intervals": sum(row["pair_status"] == "active_fire_only" for row in intervals),
                             "candidate_provider_minutes": len(minutes),
                             "candidate_minutes_with_both_catalogs": sum(row["pair_status"] == "both_catalogued" for row in minutes),
                             "archived_raw_pixels": sum(row["raw_pixels"] for row in minutes)},
              "geolocation_granule_contents_verified": False,
              "active_fire_granule_contents_verified": False,
              "observation_opportunity_verified": False, "no_detection_count": None,
              "interpretation": "Exact same-platform CMR intervals show catalogued L1 geolocation and L2 active-fire products. Catalog entries do not prove cell-level observation, cloud/quality, active-fire product completeness, or a negative detection. Unmatched candidate minutes are timestamp reconciliation questions, not failed observations."}
    report["evidence_sha256"] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def _utc(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() != timedelta(0):
        raise ValueError("CMR times must be UTC")
    return result.astimezone(timezone.utc)


def build_catalog_report(pixel_db: str | Path, regions: list[dict], snapshot: dict,
                         *, start_date: str, end_date: str, bbox: str) -> dict:
    start, end = _window(start_date, end_date)
    _bbox(bbox)
    study_id, chosen, contract = _study(regions)
    if len(chosen) != 1:
        raise ValueError("bounded catalog audit requires one study region")
    if snapshot.get("schema_version") != 1 or len(snapshot.get("queries", [])) != 2:
        raise ValueError("incomplete CMR source snapshot")
    fetched_at = _utc(snapshot["fetched_at"])
    granules, provenance = [], []
    seen_ids = set()
    for query, product in zip(snapshot["queries"], PRODUCTS.values(), strict=True):
        if query.get("product") != product or query.get("url") != catalog_url(product, start_date, end_date, bbox):
            raise ValueError("CMR source query/product contract differs")
        body = query.get("body")
        if not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != query.get("response_sha256"):
            raise ValueError("CMR source response SHA-256 differs")
        entries = json.loads(body).get("feed", {}).get("entry", [])
        hits = query.get("cmr_hits")
        if type(hits) is not int or hits > PAGE_SIZE or hits != len(entries):
            raise ValueError("incomplete CMR source result")
        provenance.append({"product": product, "collection_version": VERSION,
                           "query_url": query["url"], "response_sha256": query["response_sha256"],
                           "cmr_hits": hits})
        for entry in entries:
            identifier = entry.get("id")
            name = entry.get("producer_granule_id", "")
            if (not isinstance(identifier, str) or identifier in seen_ids or
                not name.startswith(product + ".") or
                not identifier.endswith("-LANCEMODIS") or
                not entry.get("collection_concept_id", "").endswith("-LANCEMODIS")):
                raise ValueError("CMR granule identity/product invalid")
            seen_ids.add(identifier)
            first, last = _utc(entry["time_start"]), _utc(entry["time_end"])
            revised = _utc(entry["updated"])
            if first >= last or last < datetime.combine(start, datetime.min.time(), timezone.utc) or \
               first > datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc):
                raise ValueError("CMR granule time outside requested window")
            if not entry.get("polygons"):
                raise ValueError("CMR granule lacks search footprint metadata")
            granules.append({"id": identifier, "product": product,
                             "provider": next(source for source, value in PRODUCTS.items() if value == product),
                             "producer_granule_id": name,
                             "collection_concept_id": entry["collection_concept_id"],
                             "start_at": first.isoformat(), "end_at": last.isoformat(),
                             "metadata_updated_at": revised.isoformat(),
                             "search_polygons": entry["polygons"]})
    granules.sort(key=lambda row: (row["start_at"], row["product"], row["id"]))
    lower, upper = start.isoformat() + "T", (end + timedelta(days=1)).isoformat() + "T"
    with closing(_read_only(Path(pixel_db))) as db:
        study = db.execute("SELECT contract_json,state FROM analytics_studies WHERE study_id=?",
                           (study_id,)).fetchone()
        if not study or study["contract_json"] != contract or study["state"] != "ready":
            raise ValueError("historical rollup is missing or building")
        minutes = [dict(row) for row in db.execute("""SELECT provider,
             substr(observed_at,1,16) AS observed_minute, COUNT(*) AS raw_pixels,
             MIN(first_captured_at) AS first_captured_at
             FROM analytics_region_pixels WHERE study_id=? AND region_id=?
             AND observed_at>=? AND observed_at<?
             GROUP BY provider,substr(observed_at,1,16)
             ORDER BY observed_minute,provider""",
             (study_id, chosen[0]["region_id"], lower, upper))]
        receipts = [dict(row) for row in db.execute("""SELECT scan_at,receipt_sha256,
             asset_manifest_sha256 FROM analytics_processed_scans WHERE study_id=? ORDER BY scan_at""",
             (study_id,))]
    matched = 0
    for row in minutes:
        if row["provider"] not in PRODUCTS:
            raise ValueError("archived FIRMS provider lacks a matching CMR product")
        observed = _utc(row["observed_minute"] + ":00+00:00")
        row["catalog_granule_ids"] = [item["id"] for item in granules
             if item["provider"] == row["provider"] and
             _utc(item["start_at"]) <= observed < _utc(item["end_at"])]
        matched += bool(row["catalog_granule_ids"])
    report = {"schema_version": 1, "status": "granule_catalog_context_only",
              "region": chosen[0], "study_id": study_id,
              "start_date": start_date, "end_date": end_date,
              "query_bbox_wgs84": bbox, "catalog_fetched_at": fetched_at.isoformat(),
              "catalog_first_available_at": None,
              "catalog_source": "NASA CMR LANCEMODIS VIIRS 375 m I-band geolocation NRT",
              "catalog_source_documentation": "https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html",
              "catalog_source_rights": "https://www.earthdata.nasa.gov/engage/open-data-services-software/data-use-policy",
              "source_queries": provenance, "granules": granules,
              "candidate_provider_minutes": minutes, "source_receipts": receipts,
              "population": {"catalog_granules": len(granules),
                             "candidate_provider_minutes": len(minutes),
                             "temporally_matched_candidate_provider_minutes": matched,
                             "archived_raw_pixels": sum(row["raw_pixels"] for row in minutes)},
              "granule_files_downloaded": False,
              "observation_opportunity_verified": False,
              "no_detection_count": None,
              "interpretation": "CMR search footprints and six-minute granule intervals give independent catalog context. Bounding-box search is not a cell-level swath/quality test. Temporal matches do not verify observation opportunity; unmatched minutes can reflect timestamp conventions or catalog differences. Empty intervals are not negative observations."}
    report["evidence_sha256"] = hashlib.sha256(_bytes(report)).hexdigest()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("fetch", "report", "fetch-active", "pair-report"):
        command = sub.add_parser(name)
        command.add_argument("--output", required=True, type=Path)
        if name != "pair-report":
            command.add_argument("--start-date", required=True)
            command.add_argument("--end-date", required=True)
            command.add_argument("--bbox", required=True)
        if name == "report":
            command.add_argument("--snapshot", required=True, type=Path)
            command.add_argument("--pixel-db", required=True, type=Path)
            command.add_argument("--regions-json", required=True, type=Path)
        if name == "pair-report":
            command.add_argument("--geolocation-report", required=True, type=Path)
            command.add_argument("--active-snapshot", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink():
        parser.error("output must be a new file")
    if args.command == "fetch":
        result = fetch_catalog_snapshot(start_date=args.start_date, end_date=args.end_date,
                                        bbox=args.bbox)
    elif args.command == "fetch-active":
        result = fetch_active_snapshot(start_date=args.start_date, end_date=args.end_date,
                                       bbox=args.bbox)
    elif args.command == "report":
        result = build_catalog_report(args.pixel_db, json.loads(args.regions_json.read_text()),
                   json.loads(args.snapshot.read_text()), start_date=args.start_date,
                   end_date=args.end_date, bbox=args.bbox)
    else:
        result = build_paired_product_report(json.loads(args.geolocation_report.read_text()),
                                             json.loads(args.active_snapshot.read_text()))
    args.output.write_bytes(_bytes(result))
    print(json.dumps({"output": str(args.output), "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()},
                     sort_keys=True))


if __name__ == "__main__":
    main()
