"""Bounded read-only acquisition of official USFS MTBS burned-area GeoJSON.

This tool fetches real historic REFERENCE perimeters, never future-fire
predictor features. Only a pinned public USFS ArcGIS FeatureServer endpoint
is queried. Network responses are never trusted without schema and geometry
validation; no incomplete/truncated reference is silently published.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from urllib.request import HTTPRedirectHandler,Request,build_opener

from .perimeter_benchmark import load_reference,MAX_REFERENCE_BYTES

OFFICIAL_LAYER=("https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/"
                "services/EDW_MTBS_v1/FeatureServer/0")
MAX_RESPONSE_BYTES=8*1024*1024
MAX_REFERENCES=500
PAGE_SIZE=100
MAX_PAGES=6
MIN_YEAR=1984
MAX_YEAR=2100

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ValueError("MTBS endpoint redirect is not trusted")


def _fetch_bytes(url: str) -> bytes:
    parts=urlsplit(url)
    if parts.scheme!="https" or parts.netloc!="services2.arcgis.com" or (
        parts.path!="/FiaPA4ga0iQKduv3/arcgis/rest/services/EDW_MTBS_v1/FeatureServer/0/query"):
        raise ValueError("only pinned official MTBS GeoJSON queries are permitted")
    opener=build_opener(_NoRedirect())
    with opener.open(Request(url,headers={
          "User-Agent":"WildfireSignals-OfflineReferenceAcquisition/1",
          "Accept":"application/geo+json, application/json"}),timeout=35) as response:
        data=response.read(MAX_RESPONSE_BYTES+1)
    if len(data)>MAX_RESPONSE_BYTES:
        raise ValueError("MTBS GeoJSON response exceeds download budget")
    return data


def _bounds(bbox) -> list[tuple[float,float,float,float] | None]:
    if bbox is None:
        return [None]
    if (not isinstance(bbox,(list,tuple)) or len(bbox)!=4 or
        any(type(x) not in (int,float) or not math.isfinite(x) for x in bbox)):
        raise ValueError("expected 4 finite numbers: west south east north")
    west,south,east,north=map(float,bbox)
    if not (-180<=west<=180 and -180<=east<=180 and
            -90<=south<north<=90):
        raise ValueError("invalid WGS84 geographic bounds")
    if west==east:
        raise ValueError("zero-width bounding box")
    if west<east:
        return [(west,south,east,north)]
    # A date-line crossing selection must use two independent server envelopes.
    return [(west,south,180,north),(-180,south,east,north)]


def _query(year:int,bbox,offset:int) -> str:
    params={
      "f":"geojson",
      "where":f"YEAR = {year} AND FIRE_TYPE = 'Wildfire'",
      "outFields":"OBJECTID,FIRE_ID,FIRE_NAME,FIRE_TYPE,IG_DATE,YEAR,STARTMONTH,STARTDAY",
      "returnGeometry":"true","outSR":"4326",
      "orderByFields":"OBJECTID ASC",
      "resultOffset":str(offset),"resultRecordCount":str(PAGE_SIZE)
    }
    if bbox is not None:
        west,south,east,north=bbox
        params.update(geometry=",".join(str(x) for x in (west,south,east,north)),
                      geometryType="esriGeometryEnvelope",inSR="4326",
                      spatialRel="esriSpatialRelIntersects")
    return OFFICIAL_LAYER+"/query?"+urlencode(params)


def collect_mtbs(*,year:int,bbox=None,max_features:int=250,fetch=_fetch_bytes,
                 retrieved_at:str|None=None) -> tuple[dict,dict]:
    """Download fully paginated, strictly bounded official MTBS GeoJSON cohort.

    Results only become a valid archived sample if all query areas and pages
    finish, and the entire cohort fits within the specified max_features.
    """
    if type(year) is not int or not MIN_YEAR<=year<=MAX_YEAR:
        raise ValueError("invalid MTBS fire year")
    if type(max_features) is not int or not 1<=max_features<=MAX_REFERENCES:
        raise ValueError("max_features must be 1..500")
    bounds=_bounds(bbox)
    when=retrieved_at or datetime.now(timezone.utc).isoformat()
    if datetime.fromisoformat(when.replace("Z","+00:00")).tzinfo is None:
        raise ValueError("retrieved_at must have timezone")
    unique={}
    urls=[]
    page_count=0
    for area in bounds:
        finished=False
        for page in range(MAX_PAGES):
            url=_query(year,area,page*PAGE_SIZE)
            body=fetch(url)
            if type(body) is not bytes or len(body)>MAX_RESPONSE_BYTES:
                raise ValueError("invalid bounded MTBS response")
            try:
                result=json.loads(body)
            except (ValueError,UnicodeDecodeError) as exc:
                raise ValueError("non-GeoJSON MTBS response") from exc
            if (not isinstance(result,dict) or result.get("type")!="FeatureCollection"
                or not isinstance(result.get("features"),list)):
                raise ValueError("MTBS did not return a GeoJSON FeatureCollection")
            if len(result["features"])>PAGE_SIZE:
                raise ValueError("MTBS server exceeded requested page size")
            urls.append(url)
            page_count+=1
            for feature in result["features"]:
                if not isinstance(feature,dict) or feature.get("type")!="Feature":
                    raise ValueError("invalid MTBS feature")
                props=feature.get("properties")
                if not isinstance(props,dict):
                    raise ValueError("missing MTBS properties")
                # Deduplicate the same fire returned by both date-line envelopes;
                # reject conflicting multi-part identities rather than combining.
                keys={str(k).upper():v for k,v in props.items()}
                ident=keys.get("FIRE_ID")
                if not isinstance(ident,str) or not ident.strip():
                    raise ValueError("MTBS geometry missing FIRE_ID")
                if ident in unique and unique[ident]!=feature:
                    raise ValueError("conflicting MTBS features for same FIRE_ID")
                unique[ident]=feature
                if len(unique)>max_features:
                    raise ValueError("MTBS reference cohort exceeds max_features; narrow year/bbox")
            if len(result["features"])<PAGE_SIZE and not result.get("exceededTransferLimit"):
                finished=True
                break
        if not finished:
            raise ValueError("MTBS pagination budget reached before reference complete")
    geo={"type":"FeatureCollection","features":list(unique.values())}
    raw=json.dumps(geo,ensure_ascii=False,separators=(",",":"),sort_keys=True).encode()
    if len(raw)>MAX_REFERENCE_BYTES:
        raise ValueError("assembled reference GeoJSON exceeds file budget")
    meta={"schema_version":1,"provider":"USFS_MTBS",
          "source_url":OFFICIAL_LAYER,"requested_year":year,
          "requested_bbox":list(bbox) if bbox is not None else None,
          "retrieved_at":when,"conservative_reference_usable_not_before":when,
          "source_publication_date_independently_verified":False,
          "feature_count":len(geo["features"]),"page_count":page_count,
          "downloaded_query_urls":urls,"geojson_sha256":hashlib.sha256(raw).hexdigest(),
          "collection_complete_within_filter":True,
          "geographic_completeness_verified":False,
          "notes":"Operator-fetched official USFS MTBS historical boundary polygons; "
                  "post-event reference geometry, not live fire status or prediction inputs."}
    return geo,meta


def save_mtbs(output: str|Path,metadata: str|Path, *,
              year:int,bbox=None,max_features:int=250,fetch=_fetch_bytes,
              retrieved_at:str|None=None) -> dict:
    output,metadata=Path(output),Path(metadata)
    if output.resolve()==metadata.resolve():
        raise ValueError("GeoJSON and metadata output cannot be the same")
    if output.exists() or metadata.exists() or output.is_symlink() or metadata.is_symlink():
        raise FileExistsError("reference outputs already exist; refusing overwrite")
    geo,meta=collect_mtbs(year=year,bbox=bbox,max_features=max_features,fetch=fetch,
                          retrieved_at=retrieved_at)
    output.parent.mkdir(parents=True,exist_ok=True)
    metadata.parent.mkdir(parents=True,exist_ok=True)
    stage_geo=stage_meta=None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent,delete=False,mode="wb") as f:
            stage_geo=Path(f.name)
            f.write(json.dumps(geo,ensure_ascii=False,separators=(",",":"),
                               sort_keys=True).encode())
        # Reuse the benchmark's full geometry, ignition/date, classification
        # and reference schema validation before exposing downloaded data.
        ref=load_reference(stage_geo,source_url=OFFICIAL_LAYER,published_at=meta["retrieved_at"])
        if ref["sha256"]!=meta["geojson_sha256"] or (
                ref["included_wildfire_features"]!=meta["feature_count"]):
            raise ValueError("MTBS reference validation, type or digest mismatch")
        with tempfile.NamedTemporaryFile(dir=metadata.parent,delete=False,mode="w",
                                         encoding="utf8") as f:
            stage_meta=Path(f.name)
            json.dump(meta,f,sort_keys=True,indent=2)
            f.write("\n")
        # Files never become partially downloaded; incomplete cohorts fail
        # before this point. Roll back the first output if second rename fails.
        stage_geo.rename(output)
        try:
            stage_meta.rename(metadata)
        except Exception:
            output.unlink(missing_ok=True)
            raise
    finally:
        if stage_geo is not None:stage_geo.unlink(missing_ok=True)
        if stage_meta is not None:stage_meta.unlink(missing_ok=True)
    return meta


def main() -> None:
    p=argparse.ArgumentParser(description="Acquire bounded official MTBS GeoJSON reference")
    p.add_argument("--year",type=int,required=True)
    p.add_argument("--bbox",type=float,nargs=4,metavar=("WEST","SOUTH","EAST","NORTH"))
    p.add_argument("--max-features",type=int,default=250)
    p.add_argument("--geojson",required=True,type=Path)
    p.add_argument("--metadata",required=True,type=Path)
    args=p.parse_args()
    meta=save_mtbs(args.geojson,args.metadata,year=args.year,bbox=args.bbox,
                   max_features=args.max_features)
    print(json.dumps({"features":meta["feature_count"],"pages":meta["page_count"],
                      "metadata_file":str(args.metadata),"geojson_file":str(args.geojson),
                      "reference_file_sha256":meta["geojson_sha256"]},sort_keys=True))


if __name__=="__main__":
    main()
