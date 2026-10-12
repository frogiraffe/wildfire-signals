"""Offline retrospective perimeter–FIRMS intersection benchmark.

Perimeter polygons are *post-event reference geometry*, never point-in-time
forecast features. Pixel intersection is not an event identity, a false-positive
classification, a fire-occurrence classifier, or a calibrated risk metric.

Accepts a locally supplied MTBS or normalized GeoJSON export with explicit
provenance; no automatic network access, Cloudflare writes or secret handling.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

from .collect import FIRMS_SOURCES
from .history import _timestamp

MAX_REFERENCE_BYTES = 30 * 1024 * 1024
MAX_REFERENCE_FEATURES = 500
MAX_VERTICES_PER_FEATURE = 50_000
MAX_QUERIED_ROWS_PER_EVENT = 100_000
MAX_SCAN_ROWS_PER_EVENT = 10_000
MAX_TOTAL_ASSOCIATIONS = 300_000
SCHEMA_VERSION = 1


def _date(value) -> datetime:
    if isinstance(value, bool):
        raise ValueError("invalid date value")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError("non-finite ignition date")
        # MTBS ArcGIS IG_DATE is commonly milliseconds since Unix epoch.
        stamp = value / 1000 if abs(value) > 100_000_000_000 else value
        try:
            return datetime.fromtimestamp(stamp,timezone.utc)
        except (OverflowError,ValueError,OSError) as exc:
            raise ValueError("ignition epoch out of range") from exc
    if isinstance(value,str):
        try:
            return datetime.fromisoformat(_timestamp(value))
        except (ValueError,TypeError) as exc:
            raise ValueError("invalid ignition date") from exc
    raise ValueError("missing/unsupported ignition date")


def _fields(props: dict) -> dict:
    # Actual official MTBS ArcGIS feature export and older MTBS styles.
    fields={str(k).lower():v for k,v in props.items()}
    identity=fields.get("fire_id") or fields.get("event_id")
    kind=fields.get("fire_type") or fields.get("incid_type")
    name=fields.get("fire_name") or fields.get("incid_name") or identity
    ignition=fields.get("ig_date")
    if ignition is None:
        year=fields.get("year")
        month=fields.get("startmonth",fields.get("start_month"))
        day=fields.get("startday",fields.get("start_day"))
        if all(type(v) is int for v in (year,month,day)):
            try:
                ignition=datetime(year,month,day,tzinfo=timezone.utc)
            except ValueError as exc:
                raise ValueError("invalid fallback ignition date") from exc
    if not isinstance(identity,str) or not 0<len(identity.strip())<=160:
        raise ValueError("missing official perimeter incident ID")
    if not isinstance(kind,str):
        raise ValueError("missing MTBS fire type; prescribed/unknown cannot be silently included")
    normalized=kind.lower().strip().replace("_"," ").replace("-"," ")
    if normalized in {"wildfire","wild fire","wf"}:
        fire_class="wildfire"
    elif normalized in {"prescribed fire","prescribed burn","rx","rx fire","wildland fire use",
                        "wildland fire use (wfu)","unknown"}:
        fire_class="other_or_unknown"
    else:
        fire_class="other_or_unknown"
    if ignition is None:
        raise ValueError("missing MTBS ignition date")
    time=ignition if isinstance(ignition,datetime) else _date(ignition)
    if time.tzinfo is None:
        raise ValueError("ignition datetime missing timezone")
    if not isinstance(name,str):
        name=str(identity)
    return {"id":identity.strip(),"name":name[:160],"kind":fire_class,
            "raw_fire_type":kind[:100],"ignition_at":time.astimezone(timezone.utc).isoformat()}


def _valid_coordinate(point) -> bool:
    return (isinstance(point,list) and len(point)>=2 and
            all(type(x) in (int,float) and math.isfinite(x) for x in point[:2]) and
            -180<=point[0]<=180 and -90<=point[1]<=90)


def _rings(raw) -> tuple:
    if not isinstance(raw,list) or len(raw)<1:
        raise ValueError("polygon must have exterior ring")
    allrings=[]
    for ring in raw:
        if not isinstance(ring,list) or not 4<=len(ring)<=MAX_VERTICES_PER_FEATURE:
            raise ValueError("invalid polygon ring size")
        if any(not _valid_coordinate(p) for p in ring):
            raise ValueError("polygon vertex not WGS84 lon/lat")
        if ring[0][:2]!=ring[-1][:2]:
            raise ValueError("polygon ring not closed")
        if len({(p[0],p[1]) for p in ring[:-1]})<3:
            raise ValueError("degenerate polygon ring")
        allrings.append(tuple((float(p[0]),float(p[1])) for p in ring))
    return tuple(allrings)


def _polygons(geometry) -> tuple:
    if not isinstance(geometry,dict):
        raise ValueError("missing perimeter geometry")
    typ=geometry.get("type")
    coords=geometry.get("coordinates")
    if typ=="Polygon":
        polygons=(_rings(coords),)
    elif typ=="MultiPolygon":
        if not isinstance(coords,list) or not coords:
            raise ValueError("empty multipolygon")
        polygons=tuple(_rings(p) for p in coords)
    else:
        raise ValueError("reference geometry must be Polygon/MultiPolygon")
    if sum(len(r) for p in polygons for r in p)>MAX_VERTICES_PER_FEATURE:
        raise ValueError("too many vertices in one event")
    return polygons


def load_reference(path: str | Path, *, source_url: str,
                   published_at: str) -> dict:
    """Validate a bounded explicit MTBS GeoJSON file, preserving SHA-256.

    The SHA proves file identity, NOT authenticity of the asserted source URL.
    """
    path=Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_REFERENCE_BYTES:
        raise ValueError("reference file missing, symlinked or too large")
    ref_time=_timestamp(published_at)
    link=urlsplit(source_url)
    if link.scheme!="https" or not link.hostname or link.username or link.password:
        raise ValueError("official reference URL must be HTTPS")
    raw=path.read_bytes()
    try:
        data=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as exc:
        raise ValueError("invalid GeoJSON") from exc
    if not isinstance(data,dict) or data.get("type")!="FeatureCollection":
        raise ValueError("expected GeoJSON FeatureCollection")
    crs=data.get("crs")
    if crs is not None and crs not in ({"type":"name","properties":{"name":"EPSG:4326"}},
                                       {"type":"name","properties":{"name":"urn:ogc:def:crs:OGC::CRS84"}}):
        raise ValueError("unsupported CRS; reproject to GeoJSON WGS84 lon,lat first")
    features=data.get("features")
    if not isinstance(features,list) or len(features)>MAX_REFERENCE_FEATURES:
        raise ValueError("reference exceeds feature budget")
    included=[]
    excluded=Counter()
    identifiers=set()
    for index,feature in enumerate(features):
        if not isinstance(feature,dict) or feature.get("type")!="Feature":
            raise ValueError("invalid reference feature")
        props=feature.get("properties")
        if not isinstance(props,dict):
            raise ValueError("missing source attributes")
        metadata=_fields(props)
        if metadata["kind"]!="wildfire":
            excluded["prescribed_or_unknown_fire_type"]+=1
            continue
        if metadata["id"] in identifiers:
            raise ValueError("duplicate official fire identity; dissolve multipart features first")
        identifiers.add(metadata["id"])
        polygons=_polygons(feature.get("geometry"))
        included.append({**metadata,"polygons":polygons,"feature_index":index})
    return {"sha256":hashlib.sha256(raw).hexdigest(),"source_url":source_url,
            "published_at":ref_time,"reference_type":"post_event_burned_area_boundary",
            "claimed_dataset":"MTBS_or_explicitly_mapped_reference",
            "source_authenticity_verified":False,
            "perimeters":included,"excluded":dict(excluded),
            "supplied_features":len(features),"included_wildfire_features":len(included)}


def _unwrap_ring(ring: tuple, query_lon: float) -> list[tuple[float,float]]:
    """Represent short antimeridian-crossing edges continuously near query point."""
    x0=((ring[0][0]-query_lon+180)%360)-180
    line=[(x0,ring[0][1])]
    for p,q in zip(ring,ring[1:]):
        delta=((q[0]-p[0]+180)%360)-180
        line.append((line[-1][0]+delta,q[1]))
    # Rings spanning >180° cannot be interpreted reliably by this minimal
    # algorithm. Explicitly reject instead of producing deceptive matches.
    if max(x for x,y in line)-min(x for x,y in line)>180:
        raise ValueError("wide longitude ring unsupported; split polygon in GIS")
    return line


def _point_in_ring(lat:float,lon:float,ring:tuple) -> bool:
    line=_unwrap_ring(ring,lon)
    inside=False
    for (x1,y1),(x2,y2) in zip(line,line[1:]):
        # Points exactly on an edge count as inside the outer boundary.
        cross=(0-x1)*(y2-y1)-(lat-y1)*(x2-x1)
        if (abs(cross)<1e-10 and min(x1,x2)-1e-10<=0<=max(x1,x2)+1e-10
                and min(y1,y2)-1e-10<=lat<=max(y1,y2)+1e-10):
            return True
        if (y1>lat)!=(y2>lat):
            intersection=x1+(lat-y1)*(x2-x1)/(y2-y1)
            if 0<intersection:inside=not inside
    return inside


def point_in_perimeter(lat:float,lon:float,polygons:tuple) -> bool:
    if not all(type(z) in (int,float) and math.isfinite(z) for z in (lat,lon)):
        raise ValueError("invalid observation point")
    for polygon in polygons:
        if _point_in_ring(lat,lon,polygon[0]) and not any(
                _point_in_ring(lat,lon,hole) for hole in polygon[1:]):
            return True
    return False


def _readonly(path:Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"pixel archive unavailable: {path}")
    uri="file:"+quote(str(path.resolve()),safe="/")+"?mode=ro"
    db=sqlite3.connect(uri,uri=True)
    db.row_factory=sqlite3.Row
    return db


def benchmark_perimeters(db_path: str | Path, ref: dict, *,
                         as_of: str, observation_days: int=14) -> dict:
    """Positive-only *retrospective* overlap audit of raw pixels vs final perimeters."""
    cutoff=_timestamp(as_of)
    if type(observation_days) is not int or not 1<=observation_days<=30:
        raise ValueError("observation_days must be 1..30")
    if _timestamp(ref["published_at"])>cutoff:
        raise ValueError("reference was not published by evaluation cutoff")
    records=[]
    totals=Counter()
    total_pixel_links=0
    with closing(_readonly(Path(db_path))) as db:
        for fire in ref["perimeters"]:
            start=datetime.fromisoformat(fire["ignition_at"])
            end=start+timedelta(days=observation_days)
            if end>datetime.fromisoformat(cutoff):
                totals["reference_window_not_elapsed"]+=1
                continue
            start_s=start.isoformat()
            end_s=end.isoformat()
            scans=db.execute("""SELECT scan_at,captured_at,source_states_json
                FROM pixel_scans WHERE scan_at >= ? AND scan_at < ? AND captured_at <= ?
                ORDER BY scan_at LIMIT ?""",
                (start_s,end_s,cutoff,MAX_SCAN_ROWS_PER_EVENT+1)).fetchall()
            if len(scans)>MAX_SCAN_ROWS_PER_EVENT:
                raise ValueError("too many source scans for one event")
            source_states=Counter()
            for scan in scans:
                for source,status in json.loads(scan["source_states_json"]).items():
                    source_states[source+":"+status]+=1

            rows=db.execute("""SELECT source_record_id,provider,observed_at,
                   first_captured_at,latitude,longitude
                FROM pixel_observations
                WHERE observed_at >= ? AND observed_at < ?
                  AND first_captured_at <= ?
                ORDER BY observed_at,source_record_id LIMIT ?""",
                (start_s,end_s,cutoff,MAX_QUERIED_ROWS_PER_EVENT+1)).fetchall()
            if len(rows)>MAX_QUERIED_ROWS_PER_EVENT:
                raise ValueError("raw pixel query would be truncated; reduce input cohort")
            hits=[]
            sensor_hits=Counter()
            for row in rows:
                if point_in_perimeter(row["latitude"],row["longitude"],fire["polygons"]):
                    sensor_hits[row["provider"]]+=1
                    total_pixel_links+=1
                    if total_pixel_links>MAX_TOTAL_ASSOCIATIONS:
                        raise ValueError("benchmark exceeds association safety limit")
                    hits.append(row)
            if not scans:
                collection="no_captured_scans"
            elif any(v not in ("complete",) for scan in scans
                     for v in json.loads(scan["source_states_json"]).values()):
                collection="incomplete_source_scans"
            else:
                collection="scan_receipts_present_no_completeness_proof"
            if collection=="no_captured_scans":
                outcome="unassessed_no_collector_evidence"
            else:
                outcome=("intersection_observed" if hits else "no_intersection_in_archived_pixels")
            totals[outcome]+=1
            records.append({
                "fire_id":fire["id"],"fire_name":fire["name"],
                "ignition_at":fire["ignition_at"],
                "window_end_at":end_s,"source_fire_type":fire["raw_fire_type"],
                "retrospective_reference":True,"dataset_polygon_index":fire["feature_index"],
                "available_scan_receipts":len(scans),
                "source_scan_status_counts":dict(sorted(source_states.items())),
                "collection_evidence":collection,"outcome":outcome,
                "pixels_intersecting_final_perimeter":len(hits),
                "intersecting_pixels_by_sensor":dict(sorted(sensor_hits.items())),
                "first_intersecting_pixel_observed_at":hits[0]["observed_at"] if hits else None,
                "first_intersecting_pixel_captured_at":min(
                    (x["first_captured_at"] for x in hits),default=None),
                "not_negative_label":True,
            })
    with_scans=sum(x["available_scan_receipts"]>0 for x in records)
    intersected=sum(x["pixels_intersecting_final_perimeter"]>0 for x in records
                    if x["available_scan_receipts"]>0)
    return {
        "schema_version":SCHEMA_VERSION,
        "purpose":"retrospective_positive_only_perimeter_overlap",
        "evaluation_cutoff":cutoff,"observation_days":observation_days,
        "reference":{"file_sha256":ref["sha256"],"source_url":ref["source_url"],
                     "claimed_dataset":ref["claimed_dataset"],
                     "source_authenticity_verified":False,
                     "published_at":ref["published_at"],
                     "supplied_features":ref["supplied_features"],
                     "included_wildfire_features":ref["included_wildfire_features"],
                     "excluded":ref["excluded"]},
        "perimeters_after_cutoff_excluded":totals["reference_window_not_elapsed"],
        "evaluated_reference_perimeters":len(records),
        "with_any_eligible_collector_receipts":with_scans,
        "reference_polygons_with_pixel_intersections":intersected,
        "reference_overlap_fraction_given_some_receipts":(
            intersected/with_scans if with_scans else None),
        "total_pixel_polygon_intersections":total_pixel_links,
        "source_observation_completeness_verified":False,
        "valid_negative_labels_created":0,
        "independent_wildfire_detection_accuracy_established":False,
        "wildfire_prediction_or_spread_skill_established":False,
        "outcomes":dict(sorted(totals.items())),
        "events":records,
        "warnings":[
            "This is a retrospective comparison with POST-EVENT burned-area boundaries, not a prospective prediction test.",
            "The benchmark uses only supplied wildfire reference polygons; prescribed fire/unknown classes are excluded.",
            "No-intersection, absent pixels, partial scans and absent scans are NOT independently valid non-fire labels.",
            "Some archived receipts do not prove satellite overpass completeness; this is NOT sensitivity or false-positive rate.",
            "Only pixels actually captured by evaluation cutoff are used; retrospective perimeter geometry is never model input.",
            "A point within a final perimeter is spatial overlap, NOT proof it was actively burning when the pixel was sensed.",
            "Dataset provenance URL is provided by the operator; downloaded-file authenticity is not independently verified.",
            "The analyzed cohort can omit small or unmapped fires; a positive-only fraction is not global model performance."
        ],
    }


def render_html(report: dict) -> str:
    esc=lambda x: html.escape(str(x),quote=True)
    rows=["""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wildfire Signals | Retrospective Perimeter Overlap</title>
<style>
:root{font-family:system-ui,sans-serif;background:#11212b;color:#edf3f4}
body{max-width:1120px;margin:auto;padding:22px;line-height:1.5}
h1{font-size:1.7rem}h2{font-size:1.2rem}
header,section,details{padding:16px;margin-bottom:12px;border-radius:10px;
background:#1c343f;border:1px solid #395661}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px}
.summary div{background:#26444d;border-radius:8px;padding:12px}
.summary strong{font-size:1.6rem;display:block}
.warning{color:#ffd098}
summary{cursor:pointer;font-weight:650}
table{border-collapse:collapse;width:100%;font-size:.85rem}
th,td{padding:7px;border-bottom:1px solid #3d5862;text-align:left;overflow-wrap:anywhere}
a{color:#9bdad7}
@media(max-width:700px){body{padding:9px}table{font-size:.7rem}}
</style></head><body>"""]
    rows.append(f"<header><h1>Retrospective Burned-Area Overlap</h1>"
                f"<p>Evaluation cutoff: {esc(report['evaluation_cutoff'])}</p>"
                f"<p class='warning'>This is NOT wildfire prediction accuracy, "
                f"perimeter growth or an independently validated detection rate.</p></header>")
    rows.append("<section class='summary'>")
    for label,value in (("Wildfire references evaluated",report["evaluated_reference_perimeters"]),
                        ("References with any scan receipts",report["with_any_eligible_collector_receipts"]),
                        ("References with pixel intersection",report["reference_polygons_with_pixel_intersections"]),
                        ("Spatial pixel–polygon intersections",report["total_pixel_polygon_intersections"])):
        rows.append(f"<div><strong>{esc(value)}</strong>{esc(label)}</div>")
    rows.append("</section><section><h2>Reference and interpretation</h2>")
    rows.append(f"<p>Reference source asserted by operator: <a rel='noopener noreferrer' "
                f"href='{esc(report['reference']['source_url'])}'>{esc(report['reference']['source_url'])}</a></p>")
    rows.append(f"<p>Reference file SHA-256: {esc(report['reference']['file_sha256'])}</p>")
    for note in report["warnings"]:
        rows.append(f"<p class='warning'>{esc(note)}</p>")
    rows.append("</section><section><h2>Individual reference perimeters</h2>")
    for item in report["events"]:
        rows.append(f"<details><summary>{esc(item['fire_id'])} · {esc(item['fire_name'])} — "
                    f"{esc(item['outcome'])}</summary>")
        rows.append("<table><tbody>")
        for label,key in (("Ignition timestamp","ignition_at"),
                          ("Retrospective window end","window_end_at"),
                          ("Matched raw pixels","pixels_intersecting_final_perimeter"),
                          ("Available collection receipts","available_scan_receipts"),
                          ("Collection evidence","collection_evidence"),
                          ("First observed pixel","first_intersecting_pixel_observed_at"),
                          ("First captured pixel","first_intersecting_pixel_captured_at")):
            rows.append(f"<tr><th>{esc(label)}</th><td>{esc(item[key])}</td></tr>")
        rows.append("</tbody></table></details>")
    rows.append("</section></body></html>")
    return "\n".join(rows)


def main() -> None:
    p=argparse.ArgumentParser(description="Offline positive-only MTBS perimeter/FIRMS comparison")
    p.add_argument("--pixel-db",type=Path,required=True)
    p.add_argument("--geojson",type=Path,required=True)
    p.add_argument("--source-url",required=True)
    p.add_argument("--reference-published-at",required=True)
    p.add_argument("--as-of",required=True)
    p.add_argument("--observation-days",type=int,default=14)
    p.add_argument("--json",type=Path)
    p.add_argument("--html",type=Path)
    p.add_argument("--overwrite",action="store_true")
    a=p.parse_args()
    if not a.json and not a.html:
        p.error("at least one of --json or --html is required")
    outputs=[x for x in (a.json,a.html) if x is not None]
    if len({x.resolve() for x in outputs})!=len(outputs):
        p.error("outputs must be different files")
    if any(x.resolve() in (a.pixel_db.resolve(),a.geojson.resolve()) for x in outputs):
        p.error("report cannot overwrite reference GeoJSON or raw pixel SQLite database")
    if any(x.exists() and (not a.overwrite or not x.is_file()) for x in outputs):
        p.error("existing output requires --overwrite and must be a regular file")
    ref=load_reference(a.geojson,source_url=a.source_url,
                       published_at=a.reference_published_at)
    result=benchmark_perimeters(a.pixel_db,ref,as_of=a.as_of,
                                observation_days=a.observation_days)
    for path,data in ((a.json,json.dumps(result,indent=2,ensure_ascii=False)+"\n"),
                      (a.html,render_html(result))):
        if path is not None:
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(data,encoding="utf-8")
    print(json.dumps({"evaluated":result["evaluated_reference_perimeters"],
                      "with_intersection":result["reference_polygons_with_pixel_intersections"],
                      "source_completeness_verified":False,
                      "reports":[str(x) for x in outputs]},sort_keys=True))


if __name__=="__main__":
    main()
