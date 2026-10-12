"""Bounded official US historical wildfire perimeter evidence ingestion and replay.

NIFC Interagency Fire Perimeter History is retrospective, incomplete, and
limited to the USA through 2019. Its polygons are positive historical evidence,
NOT prospective model features, complete occurrence labels or negative cases.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .history import _timestamp
from .region_diagnostics import distance_km

SERVICE = ("https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
           "InterAgencyFirePerimeterHistory_All_Years_View/FeatureServer/0")
QUERY_URL = SERVICE + "/query"
RIGHTS_URL = "https://data-nifc.opendata.arcgis.com/datasets/nifc::interagencyfireperimeterhistory-all-years-view/about"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_IDS = 300_000
MAX_RECORDS = 300
PAGE_SIZE = 25
MAX_VERTICES = 50_000
MAX_REPORT = 500
EARTH_KM_PER_DEG = 111.1950802335


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("official source redirected; refusing unverified destination")


def _fetch(params: dict) -> dict:
    """A single whitelisted HTTPS ArcGIS endpoint, no arbitrary URL input."""
    query = urlencode(params)
    request = Request(QUERY_URL + "?" + query,
                      headers={"User-Agent": "WildfireSignals-OfflineResearch/1",
                               "Accept": "application/json"})
    with build_opener(_RejectRedirects()).open(request, timeout=45) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("official response exceeded byte limit")
    obj = json.loads(raw)
    if not isinstance(obj, dict) or obj.get("error"):
        raise ValueError(f"official service returned invalid response: {str(obj)[:200]}")
    return obj


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      allow_nan=False, separators=(",", ":"))


def _rings(geometry: dict) -> list[list[list[float]]]:
    if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError("NIFC polygon geometry required")
    polygons = ([geometry.get("coordinates")] if geometry["type"] == "Polygon"
                else geometry.get("coordinates"))
    if not isinstance(polygons, list) or not polygons:
        raise ValueError("missing polygon coordinates")
    rings = []
    count = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("invalid polygon")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise ValueError("invalid polygon ring")
            for point in ring:
                if (not isinstance(point, list) or len(point) < 2
                        or type(point[0]) not in (int, float)
                        or type(point[1]) not in (int, float)
                        or not math.isfinite(point[0]) or not math.isfinite(point[1])
                        or not -180 <= point[0] <= 180 or not -90 <= point[1] <= 90):
                    raise ValueError("polygon coordinate invalid")
                count += 1
                if count > MAX_VERTICES:
                    raise ValueError("geometry exceeds vertex budget")
            if ring[0][:2] != ring[-1][:2]:
                raise ValueError("polygon ring not closed")
            rings.append(ring)
    return rings


def _feature(obj: dict, year: int, expected: set[int]) -> tuple:
    if not isinstance(obj, dict) or obj.get("type") != "Feature":
        raise ValueError("non-GeoJSON perimeter feature")
    props = obj.get("properties")
    if not isinstance(props, dict):
        raise ValueError("perimeter attributes absent")
    oid = props.get("OBJECTID")
    if type(oid) is not int or oid not in expected or props.get("FIRE_YEAR_INT") != year:
        raise ValueError("perimeter identity or year mismatch")
    geometry = obj.get("geometry")
    _rings(geometry)
    guid = props.get("GlobalID")
    source_identity = (str(guid).casefold() if isinstance(guid, str) and guid.strip()
                       else f"objectid:{oid}")
    raw = _canonical({"type": "Feature", "properties": props, "geometry": geometry})
    digest = hashlib.sha256(raw.encode()).hexdigest()
    acres = props.get("GIS_ACRES")
    if acres is not None and (type(acres) not in (int, float)
                              or not math.isfinite(acres) or acres < 0):
        raise ValueError("invalid source-reported polygon acreage")
    return (source_identity, oid, year, str(props.get("INCIDENT") or ""),
            acres, digest, _canonical(geometry), _canonical(props))


def _create(db: sqlite3.Connection) -> None:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS perimeter_fetches (
        batch_id TEXT PRIMARY KEY,
        captured_at TEXT NOT NULL,
        fire_year INTEGER NOT NULL,
        total_service_ids INTEGER NOT NULL,
        selected_ids INTEGER NOT NULL,
        ids_sha256 TEXT NOT NULL,
        source_url TEXT NOT NULL,
        rights_url TEXT NOT NULL,
        subset_only INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS perimeter_versions (
        batch_id TEXT NOT NULL REFERENCES perimeter_fetches(batch_id),
        source_identity TEXT NOT NULL,
        object_id INTEGER NOT NULL,
        fire_year INTEGER NOT NULL,
        name TEXT NOT NULL,
        source_acres REAL,
        feature_sha256 TEXT NOT NULL,
        geometry_json TEXT NOT NULL,
        attributes_json TEXT NOT NULL,
        PRIMARY KEY(batch_id,source_identity)
    );
    CREATE INDEX IF NOT EXISTS perimeter_lookup
        ON perimeter_versions(fire_year,source_identity);
    CREATE INDEX IF NOT EXISTS perimeter_capture
        ON perimeter_fetches(captured_at, fire_year);
    """)


def sync_year(database: str | Path, *, year: int, max_records: int = 100,
              get_json=_fetch, clock=None) -> dict:
    """Retrieve a stable set of official object IDs, fetch full GeoJSON pages.

    All pages are checked before any DB rows are committed. An explicit cap
    creates a labeled subset; never claim a complete US wildfire inventory.
    """
    if type(year) is not int or not 1900 <= year <= 2019:
        raise ValueError("historical NIFC IFPH supports requested study years only through 2019")
    if type(max_records) is not int or not 1 <= max_records <= MAX_RECORDS:
        raise ValueError(f"max_records must be 1..{MAX_RECORDS}")
    ids_response = get_json({"f": "json", "where": f"FIRE_YEAR_INT = {year}",
                             "returnIdsOnly": "true"})
    ids = ids_response.get("objectIds")
    if (not isinstance(ids, list) or len(ids) > MAX_IDS or
            any(type(x) is not int or x < 0 for x in ids) or len(ids) != len(set(ids))):
        raise ValueError("official ID response malformed, duplicated or too large")
    ids = sorted(ids)
    wanted = ids[:max_records]
    selected = []
    for index in range(0, len(wanted), PAGE_SIZE):
        subset = wanted[index:index + PAGE_SIZE]
        result = get_json({"f": "geojson", "objectIds": ",".join(map(str, subset)),
                           "outFields": "*", "outSR": "4326",
                           "returnGeometry": "true", "orderByFields": "OBJECTID"})
        if not isinstance(result, dict) or result.get("type") != "FeatureCollection":
            raise ValueError("official GeoJSON page missing")
        rows = result.get("features")
        if not isinstance(rows, list) or len(rows) != len(subset):
            raise ValueError("missing or incomplete GeoJSON perimeter page")
        expected = set(subset)
        parsed = [_feature(row, year, expected) for row in rows]
        returned = [item[1] for item in parsed]
        if set(returned) != expected or len(returned) != len(set(returned)):
            raise ValueError("GeoJSON page IDs do not equal requested source IDs")
        selected.extend(parsed)
    identities = [item[0] for item in selected]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate official GlobalID across different perimeter IDs")
    now = clock() if clock is not None else datetime.now(timezone.utc).isoformat()
    captured = _timestamp(now)
    ids_digest = hashlib.sha256(_canonical(ids).encode()).hexdigest()
    signature = _canonical([captured, year, ids_digest, [(r[0], r[5]) for r in selected]])
    batch_id = hashlib.sha256(signature.encode()).hexdigest()
    db_path = Path(database)
    if db_path.exists() and (db_path.is_symlink() or not db_path.is_file()):
        raise ValueError("invalid database destination")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as db:
        _create(db)
        db.commit()
        try:
            db.execute("BEGIN")
            db.execute("""INSERT OR IGNORE INTO perimeter_fetches
                (batch_id,captured_at,fire_year,total_service_ids,selected_ids,
                 ids_sha256,source_url,rights_url,subset_only)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (batch_id,captured,year,len(ids),len(selected),ids_digest,
                 SERVICE,RIGHTS_URL,int(len(selected)<len(ids))))
            db.executemany("""INSERT OR IGNORE INTO perimeter_versions
                (batch_id,source_identity,object_id,fire_year,name,source_acres,
                 feature_sha256,geometry_json,attributes_json)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                [(batch_id,*r) for r in selected])
            db.commit()
        except Exception:
            db.rollback()
            raise
    return {"batch_id":batch_id, "captured_at":captured, "fire_year":year,
            "official_source":SERVICE,"rights_url":RIGHTS_URL,
            "total_source_ids":len(ids),"fetched_perimeters":len(selected),
            "subset_only":len(selected)<len(ids), "ids_sha256":ids_digest,
            "data_complete_for_fire_occurrence":False,
            "retrospective_not_as_of_features":True,
            "source_scope":"US retrospective interagency perimeter history through 2019"}


def _xy(lat: float, lon: float, center: tuple[float, float]) -> tuple[float,float]:
    dlon = (lon-center[1]+180)%360-180
    return (EARTH_KM_PER_DEG*dlon*math.cos(math.radians(center[0])),
            EARTH_KM_PER_DEG*(lat-center[0]))


def _in_ring(x: float, y: float, ring: list[tuple[float,float]]) -> bool:
    inside = False
    for i in range(len(ring)):
        a,b=ring[i],ring[(i+1)%len(ring)]
        if (a[1] > y) != (b[1] > y):
            cross = (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]
            if x < cross:inside=not inside
    return inside


def _edge_distance(a:tuple[float,float], b:tuple[float,float]) -> float:
    dx,dy=b[0]-a[0],b[1]-a[1]
    dot=dx*dx+dy*dy
    t=max(0.0,min(1.0,-(a[0]*dx+a[1]*dy)/dot)) if dot else 0.0
    return math.hypot(a[0]+t*dx,a[1]+t*dy)


def intersects_circle(geometry: dict, *, latitude: float, longitude: float,
                      radius_km: float) -> bool:
    """Local-azimuth approximation for bounded study circles, including dateline.

    Intended only as a filter for manual examination, NOT a geodetic area or
    proof a fire covers a sampling location.
    """
    if (not all(type(v) in (int,float) and math.isfinite(v)
                for v in (latitude,longitude,radius_km))
            or not -90<=latitude<=90 or not -180<=longitude<=180
            or not 0<radius_km<=250):
        raise ValueError("search circle must be bounded to 250 km")
    coordinates = ([geometry["coordinates"]] if geometry["type"]=="Polygon"
                   else geometry["coordinates"])
    for polygon in coordinates:
        rings = [[_xy(p[1],p[0],(latitude,longitude)) for p in r] for r in polygon]
        if any(_edge_distance(a,b)<=radius_km for ring in rings
               for a,b in zip(ring,ring[1:])):
            return True
        # Center lies in outer ring and not inside any hole.
        if _in_ring(0,0,rings[0]) and not any(
                _in_ring(0,0,hole) for hole in rings[1:]):
            return True
    return False


def report(database: str | Path, *, at: str, year: int | None = None,
           latitude: float | None = None, longitude: float | None = None,
           radius_km: float | None = None, limit: int = 200) -> dict:
    cutoff=_timestamp(at)
    if type(limit) is not int or not 1<=limit<=MAX_REPORT:
        raise ValueError("report limit must be 1..500")
    if year is not None and (type(year) is not int or not 1900<=year<=2019):
        raise ValueError("invalid historical fire year")
    use_circle=any(x is not None for x in (latitude,longitude,radius_km))
    if use_circle and (latitude is None or longitude is None or radius_km is None):
        raise ValueError("all circle dimensions required")
    if use_circle:
        intersects_circle({"type":"Polygon","coordinates":[[
            [0.0,0.0],[0.0,0.0],[0.0,0.0],[0.0,0.0]]]},
            latitude=latitude,longitude=longitude,radius_km=radius_km)
    path=Path(database)
    if not path.is_file():
        raise FileNotFoundError(path)
    db=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True)
    db.row_factory=sqlite3.Row
    try:
        query="""SELECT f.batch_id,f.captured_at,f.fire_year,f.subset_only,
                        f.total_service_ids,v.source_identity,v.object_id,v.name,
                        v.source_acres,v.feature_sha256,v.geometry_json,v.attributes_json
                 FROM perimeter_versions v JOIN perimeter_fetches f
                   ON f.batch_id=v.batch_id
                 WHERE f.captured_at<=?"""
        params=[cutoff]
        if year is not None:
            query+=" AND f.fire_year=?"
            params.append(year)
        query+=" ORDER BY f.captured_at DESC,f.batch_id DESC,v.object_id"
        rows=db.execute(query,params)
        seen=set()
        matches=[]
        considered=0
        source_batches=set()
        any_subset=False
        for r in rows:
            key=(r["fire_year"],r["source_identity"])
            if key in seen:
                continue
            seen.add(key)
            considered+=1
            any_subset |= bool(r["subset_only"])
            source_batches.add(r["batch_id"])
            geometry=json.loads(r["geometry_json"])
            if use_circle and not intersects_circle(geometry,latitude=latitude,
                                                     longitude=longitude,radius_km=radius_km):
                continue
            matches.append({"provider":"nifc_ifph_retrospective","source_identity":r["source_identity"],
                "object_id":r["object_id"],"fire_year":r["fire_year"],
                "name":r["name"],"source_reported_acres":r["source_acres"],
                "geometry":geometry,"source_attributes":json.loads(r["attributes_json"]),
                "feature_sha256":r["feature_sha256"],"captured_at":r["captured_at"],
                "batch_id":r["batch_id"],"source_url":SERVICE,"rights_url":RIGHTS_URL,
                "evidence_role":"retrospective_fire_perimeter_positive_context_only"})
        output=matches[:limit]
        return {"schema_version":1,"decision_at":cutoff,
                "study_scope":{"historical_fire_year":year,"usa_provider_only":True,
                    "circle":({"latitude":latitude,"longitude":longitude,"radius_km":radius_km}
                              if use_circle else None)},
                "visible_unique_source_ids":considered,"matches":len(matches),
                "shown":len(output),"truncated":len(matches)>limit,
                "source_batches":len(source_batches),
                "any_source_batch_subset_only":bool(any_subset),
                "events":output,"independent_positive_context_only":True,
                "valid_negative_labels_created":0,"model_feature_ready":False,
                "notes":[
                    "NIFC IFPH is an incomplete US historical perimeter registry through 2019.",
                    "Archive capture time controls as-of visibility; source FIRE_YEAR is not data availability time.",
                    "Geometry-circle intersection uses local approximation and is for evidence exploration only.",
                    "No absent perimeter is a fire-negative; no occurrence model is trained or evaluated.",
                    "Retrospectively published final perimeters are not valid contemporaneous prediction features.",
                ]}
    finally:
        db.close()


def _write(path: Path, payload: dict, inputs: list[Path]) -> None:
    if path.resolve() in {p.resolve() for p in inputs} or path.exists():
        raise ValueError("output cannot overwrite source DB or existing file")
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as target:
        json.dump(payload,target,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)
        target.write("\n")


def main() -> None:
    parser=argparse.ArgumentParser(description="NIFC retrospective fire perimeter research evidence")
    actions=parser.add_subparsers(dest="action",required=True)
    sync=actions.add_parser("sync",help="Fetch an explicitly bounded historical fire-year set")
    sync.add_argument("--db",required=True,type=Path)
    sync.add_argument("--year",required=True,type=int)
    sync.add_argument("--max-records",type=int,default=100)
    view=actions.add_parser("report",help="Inspect archived perimeter evidence as-of capture time")
    view.add_argument("--db",required=True,type=Path)
    view.add_argument("--at",required=True)
    view.add_argument("--year",type=int)
    view.add_argument("--latitude",type=float)
    view.add_argument("--longitude",type=float)
    view.add_argument("--radius-km",type=float)
    view.add_argument("--limit",type=int,default=200)
    view.add_argument("--output",required=True,type=Path)
    view.add_argument("--geojson",type=Path)
    args=parser.parse_args()
    if args.action=="sync":
        print(json.dumps(sync_year(args.db,year=args.year,max_records=args.max_records),
                         sort_keys=True))
        return
    payload=report(args.db,at=args.at,year=args.year,latitude=args.latitude,
                   longitude=args.longitude,radius_km=args.radius_km,limit=args.limit)
    destinations=[args.output]+([args.geojson] if args.geojson else [])
    if len(set(p.resolve() for p in destinations))!=len(destinations):
        parser.error("output and GeoJSON must be different")
    if any(p.resolve()==args.db.resolve() or p.exists() for p in destinations):
        parser.error("refusing to overwrite database or existing output")
    _write(args.output,payload,[args.db])
    if args.geojson:
        features=[{"type":"Feature","geometry":event["geometry"],"properties":{
            key:event[key] for key in ("provider","source_identity","object_id",
               "fire_year","name","source_reported_acres","captured_at",
               "batch_id","feature_sha256","evidence_role")}}
            for event in payload["events"]]
        collection={"type":"FeatureCollection","features":features,
            "properties":{"as_of":payload["decision_at"],"truncated":payload["truncated"],
                          "independent_positive_context_only":True}}
        _write(args.geojson,collection,[args.db])
    print(json.dumps({"matches":payload["matches"],"shown":payload["shown"],
                      "truncated":payload["truncated"],"output":str(args.output)},
                     sort_keys=True))


if __name__=="__main__":
    main()
