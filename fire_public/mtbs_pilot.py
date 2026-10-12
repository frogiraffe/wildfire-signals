"""Real USGS/USFS MTBS large-fire point inventory, distinct from NIFC perimeters.

A bounded, source-verified *retrospective* dual-provider investigation.
MTBS is a satellite/post-fire assessment inventory of large wildland fires,
including prescribed burns. Reporting scope differs from NIFC and its agency
input records may overlap: NOT independent binary ground truth, no non-fires.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from socket import EAI_AGAIN, gaierror
from time import sleep
from urllib.error import URLError
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .history import _timestamp
from .official_perimeters import _RejectRedirects, _canonical, intersects_circle
from .perimeter_study import study_report
from .region_diagnostics import distance_km

BASE="https://apps.fs.usda.gov/arcx/rest/services/EDW/EDW_MTBS_01/MapServer"
YEARS={2017:68,2018:70}
PROVIDER="MTBS USGS-USFS large-fire occurrence centroid"
RIGHTS="https://catalog.data.gov/dataset/monitoring-trends-in-burn-severity-fire-occurrence-locations-feature-layer"
MAX_BYTES=4*1024*1024
MAX_IDS=200_000
MAX_SAMPLE=20
MAX_FEATURES=40


def _json_http(url: str, params: dict) -> tuple[dict,bytes]:
    """Fixed source endpoints only, no redirects or arbitrary caller URL."""
    request=Request(url+"?"+urlencode(params),headers={
        "User-Agent":"WildfireSignals-MTBS-Research/1",
        "Accept":"application/json"})
    # USDA's public DNS intermittently returns EAI_AGAIN from GitHub runners.
    # Retry *only* that explicitly temporary resolver fault, not HTTP errors,
    # schema changes, bad permissions, permanent DNS failures or rate limits.
    # Five bounded calls at most with a 45-second total sleep budget; all attempts preserve the same exact URL.
    for attempt in range(5):
        try:
            with build_opener(_RejectRedirects()).open(request,timeout=45) as response:
                raw=response.read(MAX_BYTES+1)
            break
        except URLError as error:
            if (attempt==4 or not isinstance(error.reason,gaierror)
                    or error.reason.errno!=EAI_AGAIN):
                raise
            sleep(3*(2**attempt))
    if not raw or len(raw)>MAX_BYTES:
        raise ValueError("MTBS source response empty or over 4 MiB budget")
    result=json.loads(raw)
    if not isinstance(result,dict) or result.get("error"):
        raise ValueError("MTBS government source query failed or changed")
    return result,raw


def _meta(year:int, get=None) -> tuple[dict,bytes]:
    url=f"{BASE}/{YEARS[year]}"
    return (_json_http(url,{"f":"json"}) if get is None
            else get(url,{"f":"json"}))


def _query(year:int,params:dict,get=None)->tuple[dict,bytes]:
    url=f"{BASE}/{YEARS[year]}/query"
    return (_json_http(url,params) if get is None else get(url,params))


def _schema(meta:dict,year:int)->dict:
    fields=meta.get("fields")
    if not isinstance(fields,list):
        raise ValueError("MTBS feature layer schema missing")
    names={str(f.get("name","")).casefold() for f in fields if isinstance(f,dict)}
    needed={"objectid","fire_id","fire_name","fire_type","ig_date","acres"}
    if (meta.get("id")!=YEARS[year] or
        meta.get("name")!=f"{year} Fire Occurrence Locations" or
        meta.get("geometryType")!="esriGeometryPoint" or
        "Query" not in str(meta.get("capabilities","")) or
        not needed.issubset(names) or
        "json" not in str(meta.get("supportedQueryFormats","")).casefold()):
        raise ValueError("pinned USDA MTBS point source layer or fields have drifted")
    return {
        "year":year,"layer_id":YEARS[year],
        "schema_sha256":hashlib.sha256(_canonical(meta).encode()).hexdigest(),
        "field_names":sorted(names),
    }


def _parse_feature(row:dict,year:int,expected:set[int])->dict:
    if not isinstance(row,dict) or not isinstance(row.get("attributes"),dict):
        raise ValueError("MTBS missing original ArcGIS point attributes")
    p={str(k).casefold():v for k,v in row["attributes"].items()}
    oid=p.get("objectid")
    if type(oid) is not int or oid not in expected:
        raise ValueError("unexpected MTBS object ID in point page")
    point=row.get("geometry")
    if not isinstance(point,dict):
        raise ValueError("MTBS original point geometry required")
    lon,lat=point.get("x"),point.get("y")
    if (type(lon) not in (float,int) or type(lat) not in (float,int) or
        not math.isfinite(lon) or not math.isfinite(lat) or
        not -180<=lon<=180 or not -90<=lat<=90):
        raise ValueError("invalid original MTBS WGS84 point")
    fire_id=p.get("fire_id")
    if not isinstance(fire_id,str) or not fire_id.strip():
        raise ValueError("MTBS mapped fire must retain original fire_id")
    # ArcGIS JSON dates are UTC epoch milliseconds. Some dates are absent;
    # a source's per-year layer is not by itself a verified ignition day.
    when=p.get("ig_date")
    event_at=None
    if type(when) is int:
        if not 0<=when<=4102444800000:
            raise ValueError("invalid source ignition date timestamp")
        event_at=datetime.fromtimestamp(when/1000,timezone.utc).isoformat()
    elif when is not None:
        raise ValueError("unexpected MTBS source ignition date type")
    if event_at is not None and datetime.fromisoformat(event_at).year!=year:
        raise ValueError("MTBS ignition date conflicts with official year layer")
    acres=p.get("acres")
    if acres is not None and (type(acres) not in (float,int)
                            or not math.isfinite(acres) or acres<0):
        raise ValueError("invalid reported MTBS acres attribute")
    original_sha=hashlib.sha256(_canonical(row).encode()).hexdigest()
    return {
        "fire_year_layer":year,"object_id":oid,
        "source_fire_id":fire_id.strip(),
        "source_name":str(p.get("fire_name") or ""),
        "source_fire_type":p.get("fire_type"),
        "source_reported_acres":acres,
        "source_ignition_at":event_at,
        "latitude":float(lat),"longitude":float(lon),
        "original_feature_sha256":original_sha,
        "evidence_kind":"MTBS_postfire_large_fire_assessment_point",
        "prospectively_known":False,
        "is_independent_nonfire_label":False,
    }


def _first_by_hash(ids:list[int],year:int,n:int,seed:str)->list[int]:
    return sorted(sorted(ids,key=lambda k:(
        hashlib.sha256(f"{seed}:{year}:{k}".encode()).digest(),k))[:n])


def source_sample(*,years:list[int],sample_per_year:int=4,
                  seed:str="mtbs-usfs-research-v1",get=None,clock=None)->tuple[dict,dict[str,bytes]]:
    if (not isinstance(years,list) or not 1<=len(years)<=2 or
        len(years)!=len(set(years)) or
        any(type(y) is not int or y not in YEARS for y in years)):
        raise ValueError("MTBS bounded live pilot supports 2017 and/or 2018 only")
    if type(sample_per_year) is not int or not 1<=sample_per_year<=MAX_SAMPLE:
        raise ValueError("sample_per_year must be 1..20")
    if not isinstance(seed,str) or not 1<=len(seed)<=128 or not seed.isascii():
        raise ValueError("nonempty bounded ASCII sampling seed required")
    if len(years)*sample_per_year>MAX_FEATURES:
        raise ValueError("MTBS sample exceeds 40-point research budget")
    captured=_timestamp(clock() if clock else datetime.now(timezone.utc).isoformat())
    years=sorted(years)
    archive={}
    per_year=[]
    all_points=[]
    for year in years:
        meta,meta_raw=_meta(year,get)
        schema=_schema(meta,year)
        response,id_raw=_query(year,{"f":"json","where":"1=1","returnIdsOnly":"true"},get)
        ids=response.get("objectIds")
        if (not isinstance(ids,list) or not ids or len(ids)>MAX_IDS or
            any(type(v) is not int or v<0 for v in ids) or len(set(ids))!=len(ids)):
            raise ValueError("MTBS object-ID population invalid or unavailable")
        ids=sorted(ids)
        selected=_first_by_hash(ids,year,sample_per_year,seed)
        page,page_raw=_query(year,{
            "f":"json","objectIds":",".join(map(str,selected)),"outFields":"*",
            "outSR":"4326","returnGeometry":"true"},get)
        features=page.get("features")
        if not isinstance(features,list) or len(features)!=len(selected):
            raise ValueError("MTBS returned incomplete source point sample")
        parsed=[_parse_feature(x,year,set(selected)) for x in features]
        if (len(set(x["object_id"] for x in parsed))!=len(selected) or
            set(x["object_id"] for x in parsed)!=set(selected)):
            raise ValueError("MTBS point IDs do not match sampled source IDs")
        all_points.extend(sorted(parsed,key=lambda x:x["object_id"]))
        file_info=[]
        for role,raw in (("metadata",meta_raw),("ids",id_raw),("selected-points",page_raw)):
            filename=f"mtbs-{year}-{role}.json"
            if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:
                raise ValueError("original government source bytes are missing or oversized")
            archive[filename]=raw
            file_info.append({"filename":filename,"sha256":hashlib.sha256(raw).hexdigest(),
                              "bytes":len(raw)})
        per_year.append({
            "year":year,"source_layer":f"{BASE}/{YEARS[year]}",
            "source_ids_total":len(ids),"source_ids_sha256":hashlib.sha256(
                _canonical(ids).encode()).hexdigest(),
            "sampled_ids_sha256":hashlib.sha256(_canonical(selected).encode()).hexdigest(),
            "sampled_points":len(selected),
            "selected_fraction_of_published_source_ids":round(len(selected)/len(ids),6),
            "source_metadata_sha256":schema["schema_sha256"],
            "raw_source_files":file_info,
            "source_census_of_all_fires_complete":False,
        })
    summary={
        "schema_version":1,"provider":PROVIDER,
        "source_catalog":RIGHTS,"source_capture_at":captured,
        "source_transport":("direct_fixed_usfs_https" if get is None
                            else "injected_test_transport"),
        "years":years,"sampling_seed":seed,
        "sampled_per_year_budget":sample_per_year,
        "source_years":per_year,"points":all_points,
        "sampled_source_points":len(all_points),
        "original_source_byte_files":sorted(archive),
        "point_inventory_not_full_wildfires":True,
        "point_observations_are_retrospective":True,
        "negative_fire_labels_created":0,
        "outcome_independence_established":False,
        "warnings":[
            "MTBS inventories mapped LARGE wildland fires and prescribed burns; omission is not absence.",
            "MTBS and NIFC may reuse original incident records; independent outcomes not established.",
            "MTBS points are retrospective burned-area centroids and not necessarily ignition locations.",
            "Sampled official point IDs are not a representative census of wildfire events.",
            "Source ignition-date attributes may be missing or retrospectively corrected.",
        ],
    }
    return summary,archive


def compare_archived_nifc(mtbs:dict,db:Path,*,nifc_at:str,radius_km:float=50)->dict:
    """Explore same-year spatial co-location, never mark matched fires or negatives."""
    if not isinstance(radius_km,(int,float)) or not 1<=radius_km<=100:
        raise ValueError("research co-location radius must be between 1 and 100 km")
    baseline,geometry=study_report(db,at=nifc_at,years=mtbs["years"])
    if not baseline["complete_requested_year_sample"]:
        raise ValueError("NIFC comparison archive missing source-year evidence")
    links=[]
    for point in mtbs["points"]:
        for polygon in geometry["features"]:
            p=polygon["properties"]
            if p["FIRE_YEAR_INT"]!=point["fire_year_layer"]:
                continue
            if intersects_circle(polygon["geometry"],latitude=point["latitude"],
                                 longitude=point["longitude"],radius_km=radius_km):
                links.append({
                    "mtbs_object_id":point["object_id"],
                    "mtbs_fire_id":point["source_fire_id"],
                    "nifc_object_id":p["OBJECTID"],
                    "fire_year":point["fire_year_layer"],
                    "spatially_nearby_only":True,
                    "same_incident_confirmed":False,
                })
    return {
        "schema_version":1,"nifc_as_of":baseline["decision_at"],
        "mtbs_source_capture_at":mtbs["source_capture_at"],
        "mtbs_sampled_source_points":len(mtbs["points"]),
        "nifc_sampled_source_polygons":len(geometry["features"]),
        "spatial_co_location_candidates":links,
        "search_radius_km":radius_km,
        "matching_scientific_status":"proximity_only_not_event_identity",
        "nonmatches_count_as_absent_fires":False,
        "negative_fire_labels_created":0,
        "note":"Two differently selected subsets; proximity or no proximity is not event identity, detection accuracy or validation.",
    }


def save_sample(folder:Path,summary:dict,raws:dict[str,bytes],
                comparison:dict|None=None)->None:
    """New directory only; ensure bounded archive files and rollback on failures."""
    if folder.exists() or folder.is_symlink():
        raise ValueError("research evidence destination must be new")
    folder.mkdir(parents=True,mode=0o700)
    try:
        for name,data in raws.items():
            if (not name.startswith("mtbs-") or name.count("/") or
                not name.endswith(".json") or len(data)>MAX_BYTES):
                raise ValueError("invalid raw official source evidence filename")
            with (folder/name).open("xb") as stream:
                stream.write(data)
        for name,obj in (("sample-summary.json",summary),
                         ("nifc-proximity-candidates.json",comparison)):
            if obj is not None:
                with (folder/name).open("x",encoding="utf-8") as stream:
                    json.dump(obj,stream,indent=2,ensure_ascii=False,sort_keys=True)
                    stream.write("\n")
    except BaseException:
        for f in folder.iterdir():
            if f.is_file():f.unlink()
        folder.rmdir()
        raise


def main()->None:
    parser=argparse.ArgumentParser(description="MTBS second official provider, retrospective large-fire points only")
    parser.add_argument("--year",type=int,action="append",required=True)
    parser.add_argument("--records-per-year",type=int,default=4)
    parser.add_argument("--seed",default="mtbs-usfs-research-v1")
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--nifc-db",type=Path)
    parser.add_argument("--nifc-at")
    args=parser.parse_args()
    if bool(args.nifc_db) != bool(args.nifc_at):
        parser.error("--nifc-db and --nifc-at must be supplied together")
    if args.nifc_db and args.output_dir.resolve() in (
            args.nifc_db.resolve(),args.nifc_db.parent.resolve()):
        parser.error("output must not be the NIFC database or its parent directory")
    report,bytes_by_name=source_sample(
        years=args.year,sample_per_year=args.records_per_year,seed=args.seed)
    comparison=(compare_archived_nifc(report,args.nifc_db,nifc_at=args.nifc_at)
                if args.nifc_db else None)
    save_sample(args.output_dir,report,bytes_by_name,comparison)
    print(json.dumps({
        "status":"captured_retrospective_mtbs_source_sample",
        "sampled_source_points":len(report["points"]),
        "source_years":report["years"],
        "nifc_spatial_candidate_pairs":(
            len(comparison["spatial_co_location_candidates"]) if comparison else None),
        "negative_fire_labels_created":0,
        "source_transport":report["source_transport"],
    },sort_keys=True))


if __name__=="__main__":
    main()
