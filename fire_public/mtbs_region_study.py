"""Spatially aligned research capture of NIFC and MTBS in the SAME WGS84 area/year.

Unlike independent year-wide hash samples, this queries both official ArcGIS
services with the same geographic rectangle and fire year *before* bounded
source-ID selection. Nearness and shared event names are leads, NOT validated
same-incident identity, detection skill, prospective features, or nonfire data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from .history import _timestamp
from .official_live_probe import _get_layer_metadata, validate_layer_metadata
from .official_lead_refresh import _fetch_direct
from .official_perimeters import _feature, intersects_circle, SERVICE, RIGHTS_URL, _canonical
from .mtbs_pilot import _meta, _query, _schema, _parse_feature, YEARS, BASE
from .mtbs_pilot import _first_by_hash, RIGHTS as MTBS_RIGHTS
from .perimeter_study import MAX_STUDY_POLYGONS

MAX_IDS=50000
MAX_RECORDS=40
MAX_YEARS=2
MAX_BYTES=8*1024*1024


def roi_bbox(coords: list) -> tuple[float,float,float,float]:
    if not isinstance(coords,list) or len(coords)!=4 or any(
            type(x) not in (int,float) or not math.isfinite(x) for x in coords):
        raise ValueError("ROI must be four finite WGS84 bbox coordinates")
    west,south,east,north=map(float,coords)
    if (not -180<=west<east<=180 or not -90<=south<north<=90
            or east-west>5 or north-south>5):
        raise ValueError("study ROI must be a non-wrapping WGS84 bbox <=5 x 5 degrees")
    return west,south,east,north


def _roi_query(rect: tuple[float,float,float,float]) -> dict:
    west,south,east,north=rect
    return {
        "geometry":",".join(str(x) for x in (west,south,east,north)),
        "geometryType":"esriGeometryEnvelope",
        "inSR":"4326",
        "spatialRel":"esriSpatialRelIntersects",
    }


def _raw_json(getter,params):
    raw=getter(params)
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:
        raise ValueError("original NIFC HTTP response bytes missing or oversized")
    result=json.loads(raw)
    if not isinstance(result,dict) or result.get("error"):
        raise ValueError("NIFC official region query response malformed")
    return result,raw


def _id_population(obj: dict, provider: str) -> list[int]:
    ids=obj.get("objectIds")
    if (not isinstance(ids,list) or not ids or len(ids)>MAX_IDS
            or any(type(oid) is not int or oid<0 for oid in ids)
            or len(ids)!=len(set(ids))):
        raise ValueError(f"{provider} ROI source ID list empty, duplicated or above budget")
    return sorted(ids)


def _clip_point(point: dict,roi: tuple[float,float,float,float]) -> bool:
    west,south,east,north=roi
    return (west<=point["longitude"]<=east and
            south<=point["latitude"]<=north)


def _bbox_polygon_may_intersect(geometry: dict,roi: tuple) -> bool:
    # Provider spatial query is authoritative for geometry intersection.
    # This bounding-box screen only rejects obviously unrelated responses.
    from .official_perimeters import _rings
    west,south,east,north=roi
    points=[p for ring in _rings(geometry) for p in ring]
    xs=[p[0] for p in points]
    ys=[p[1] for p in points]
    if max(ys)<south or min(ys)>north:
        return False
    # Antimeridian polygons need a specialist GIS audit; do not reject
    # solely on longitude if the source polygon crosses the date line.
    if max(xs)-min(xs)>180:
        return True
    return max(xs)>=west and min(xs)<=east


def aligned_capture(*,year:int,roi:list,limit_per_source:int=30,
                    seed:str="shared-region-v1",nifc_get=None,mtbs_get=None,
                    nifc_metadata=None,clock=None,radius_km:float=15)->tuple[dict,dict[str,bytes]]:
    if type(year) is not int or year not in YEARS:
        raise ValueError("aligned pilot supports 2017 or 2018 source years")
    rect=roi_bbox(roi)
    if type(limit_per_source) is not int or not 1<=limit_per_source<=MAX_RECORDS:
        raise ValueError("limit_per_source must be 1..40")
    if not isinstance(seed,str) or not 1<=len(seed)<=128 or not seed.isascii():
        raise ValueError("bounded ASCII source-ID selection seed required")
    if type(radius_km) not in (int,float) or not math.isfinite(radius_km) or not 1<=radius_km<=50:
        raise ValueError("candidate study radius must be finite and between 1 and 50 km")
    captured=_timestamp(clock() if clock else datetime.now(timezone.utc).isoformat())
    nifc_transport=("direct_pinned_nifc_https" if nifc_get is None and nifc_metadata is None
                    else "injected_test_transport")
    mtbs_transport=("direct_fixed_usfs_https" if mtbs_get is None
                    else "injected_test_transport")
    schema=validate_layer_metadata(_get_layer_metadata() if nifc_metadata is None else nifc_metadata())
    mtbs_meta,mtbs_meta_raw=_meta(year,mtbs_get)
    mtbs_schema=_schema(mtbs_meta,year)
    region_params=_roi_query(rect)
    get_nifc=_fetch_direct if nifc_get is None else nifc_get
    nifc_ids_data,nifc_ids_raw=_raw_json(get_nifc,{
        **region_params,"f":"json","where":f"FIRE_YEAR_INT = {year}",
        "returnIdsOnly":"true"})
    mtbs_ids_data,mtbs_ids_raw=_query(year,{
        **region_params,"f":"json","where":"1=1","returnIdsOnly":"true"},mtbs_get)
    nifc_ids=_id_population(nifc_ids_data,"NIFC")
    mtbs_ids=_id_population(mtbs_ids_data,"MTBS")
    nifc_selected=_first_by_hash(nifc_ids,year,min(len(nifc_ids),limit_per_source),
                                 "nifc:"+seed)
    mtbs_selected=_first_by_hash(mtbs_ids,year,min(len(mtbs_ids),limit_per_source),
                                 "mtbs:"+seed)
    nifc_features=[]
    # Fixed, conservative page size avoids provider response truncation.
    nifc_raws={}
    for start in range(0,len(nifc_selected),20):
        page_ids=nifc_selected[start:start+20]
        data,raw=_raw_json(get_nifc,{
            "f":"geojson","objectIds":",".join(map(str,page_ids)),
            "outFields":"*","outSR":"4326","returnGeometry":"true"})
        if data.get("type")!="FeatureCollection" or not isinstance(data.get("features"),list) or len(data["features"])!=len(page_ids):
            raise ValueError("NIFC source region polygon page incomplete")
        parsed=[_feature(x,year,set(page_ids)) for x in data["features"]]
        if {r[1] for r in parsed}!=set(page_ids) or len({r[1] for r in parsed})!=len(page_ids):
            raise ValueError("NIFC returned unexpected or repeated source IDs")
        for x,parsed_row in zip(data["features"],parsed):
            if not _bbox_polygon_may_intersect(x["geometry"],rect):
                raise ValueError("NIFC source polygon is outside requested ROI")
            nifc_features.append({
                "object_id":parsed_row[1],"source_identity":parsed_row[0],
                "name":parsed_row[3],"reported_acres":parsed_row[4],
                "feature_sha256":parsed_row[5],"geometry":x["geometry"],
                "original_attributes":x["properties"],"year":year,
            })
        nifc_raws[f"nifc-{year}-page-{start//20+1}.geojson"]=raw
    mtbs_data,mtbs_points_raw=_query(year,{
        "f":"json","objectIds":",".join(map(str,mtbs_selected)),
        "outFields":"*","outSR":"4326","returnGeometry":"true"},mtbs_get)
    features=mtbs_data.get("features")
    if not isinstance(features,list) or len(features)!=len(mtbs_selected):
        raise ValueError("MTBS source ROI point page incomplete")
    points=[_parse_feature(x,year,set(mtbs_selected)) for x in features]
    if {p["object_id"] for p in points}!=set(mtbs_selected) or len(points)!=len(set(p["object_id"] for p in points)):
        raise ValueError("MTBS returned unexpected or repeated source IDs")
    if any(not _clip_point(p,rect) for p in points):
        raise ValueError("MTBS returned a point outside requested ROI")
    candidates=[]
    for point in sorted(points,key=lambda p:p["object_id"]):
        for polygon in sorted(nifc_features,key=lambda p:p["object_id"]):
            if intersects_circle(polygon["geometry"],latitude=point["latitude"],
                                  longitude=point["longitude"],radius_km=radius_km):
                candidates.append({
                    "year":year,
                    "mtbs_fire_id":point["source_fire_id"],
                    "mtbs_object_id":point["object_id"],
                    "mtbs_name":point["source_name"],
                    "mtbs_fire_type":point["source_fire_type"],
                    "nifc_object_id":polygon["object_id"],
                    "nifc_name":polygon["name"],
                    "within_study_search_radius_only":True,
                    "same_event_verified":False,
                    "independent_outcome_verified":False,
                })
    # Keep complete selected-source context, not only candidate IDs.
    source_bytes={
        f"nifc-{year}-roi-ids.json":nifc_ids_raw,
        f"mtbs-{year}-metadata.json":mtbs_meta_raw,
        f"mtbs-{year}-roi-ids.json":mtbs_ids_raw,
        f"mtbs-{year}-roi-points.json":mtbs_points_raw,
        **nifc_raws,
    }
    evidence=[{"filename":name,"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw)}
              for name,raw in sorted(source_bytes.items())]
    report={
        "schema_version":1,"year":year,"roi_wgs84_bbox":list(rect),
        "region_query":"ArcGIS esriSpatialRelIntersects envelope",
        "retrieved_at":captured,
        "nifc_source":SERVICE,"nifc_rights":RIGHTS_URL,
        "mtbs_source":f"{BASE}/{YEARS[year]}","mtbs_rights":MTBS_RIGHTS,
        "nifc_transport":nifc_transport,"mtbs_transport":mtbs_transport,
        "nifc_metadata_sha256":schema["schema_sha256"],
        "mtbs_metadata_sha256":mtbs_schema["schema_sha256"],
        "selected_id_seed":seed,"record_limit_per_source":limit_per_source,
        "source_population":{
            "nifc_roi_object_ids":len(nifc_ids),
            "mtbs_roi_object_ids":len(mtbs_ids),
            "nifc_roi_ids_sha256":hashlib.sha256(_canonical(nifc_ids).encode()).hexdigest(),
            "mtbs_roi_ids_sha256":hashlib.sha256(_canonical(mtbs_ids).encode()).hexdigest(),
            "nifc_selected_ids_sha256":hashlib.sha256(_canonical(nifc_selected).encode()).hexdigest(),
            "mtbs_selected_ids_sha256":hashlib.sha256(_canonical(mtbs_selected).encode()).hexdigest(),
            "both_selected_records_exhaust_all_source_roi_ids":(
                len(nifc_ids)==len(nifc_selected) and len(mtbs_ids)==len(mtbs_selected)),
        },
        "nifc_polygons":sorted(nifc_features,key=lambda p:p["object_id"]),
        "mtbs_points":sorted(points,key=lambda p:p["object_id"]),
        "candidate_pairs":candidates,
        "candidate_radius_km":radius_km,
        "raw_source_files":evidence,
        "same_fire_event_identifications_verified":0,
        "negative_labels_created":0,
        "forecast_model_skill_measured":False,
        "science_caveats":[
            "The same queried area/year improves comparability of available source records, not source completeness.",
            "MTBS large-fire inventory includes prescribed burns and is not a census of wildfires.",
            "MTBS mapped centroids are not verified ignition points, and source timestamps may be retrospective.",
            "Both providers may reuse agency incident inputs; matched polygons and points are not independent confirmations.",
            "Nearness is a human-review candidate, not confirmed identity; no pair is a ground-truth label.",
            "Sources queried in the present were not necessarily available at historical prediction time.",
            "No point/polygon match is not evidence of wildfire absence or a false negative.",
        ],
    }
    return report,source_bytes


def write_capture(path:Path,report:dict,source_bytes:dict[str,bytes])->None:
    if path.exists() or path.is_symlink():
        raise ValueError("new research output directory required")
    path.mkdir(parents=True,mode=0o700)
    try:
        for item in report["raw_source_files"]:
            name=item["filename"]
            if (name not in source_bytes or "/" in name or ".." in name or
                    len(source_bytes[name])!=item["bytes"] or
                    hashlib.sha256(source_bytes[name]).hexdigest()!=item["sha256"]):
                raise ValueError("raw provider byte/file contract mismatch")
            with (path/name).open("xb") as fd:
                fd.write(source_bytes[name])
        with (path/"aligned-study.json").open("x",encoding="utf-8") as fd:
            json.dump(report,fd,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)
            fd.write("\n")
    except BaseException:
        for child in path.iterdir():
            if child.is_file():child.unlink()
        path.rmdir()
        raise


def main()->None:
    p=argparse.ArgumentParser(description="Matched geographic/year MTBS and NIFC research capture, never confirmed events")
    p.add_argument("--year",type=int,required=True,choices=tuple(YEARS))
    p.add_argument("--bbox",type=float,nargs=4,required=True,metavar=("WEST","SOUTH","EAST","NORTH"))
    p.add_argument("--limit-per-source",type=int,default=30)
    p.add_argument("--radius-km",type=float,default=15)
    p.add_argument("--seed",default="shared-region-v1")
    p.add_argument("--output-dir",type=Path,required=True)
    args=p.parse_args()
    report,source=aligned_capture(year=args.year,roi=args.bbox,
         limit_per_source=args.limit_per_source,seed=args.seed,radius_km=args.radius_km)
    write_capture(args.output_dir,report,source)
    print(json.dumps({
        "status":"same_region_official_source_candidate_study",
        "nifc_polygons":len(report["nifc_polygons"]),
        "mtbs_points":len(report["mtbs_points"]),
        "nearby_candidates":len(report["candidate_pairs"]),
        "both_providers_live":(report["nifc_transport"]=="direct_pinned_nifc_https"
              and report["mtbs_transport"]=="direct_fixed_usfs_https"),
        "independent_outcomes_verified":0,"negative_labels_created":0,
        "output":str(args.output_dir),
    },sort_keys=True))


if __name__=="__main__":
    main()
