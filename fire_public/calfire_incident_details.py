"""Original CAL FIRE individual incident page capture and source-identity checks.

A bounded retrospective investigation of CAL FIRE name leads from verified
NIFC/MTBS and CAL FIRE 2018 archive bytes. No independent event identity,
negative fire label, spatial ground truth, or forecasting success claimed.
"""
from __future__ import annotations

import argparse
from datetime import datetime,timezone
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
from urllib.request import Request,build_opener

from .calfire_incident_archive import _incident_path, _norm, parse_archive, replay as replay_archive
from .mtbs_match_review import load_study
from .official_perimeters import _RejectRedirects,intersects_circle
from .region_diagnostics import distance_km

MAX_PAGES=8
MAX_PAGE_BYTES=2*1024*1024
MAX_SUMMARY_BYTES=800*1024
SEED="calfire-incident-detail-v1"
COORD=re.compile(r"\[\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*\]")
DATE=re.compile(r"\bDate Started\s+(\d{1,2}/\d{1,2}/\d{4})(?:\s+(\d{1,2}:\d{2}\s*[AP]M))?",re.I)
ACRES=re.compile(r"\b([\d,]+)\s+Acres\b",re.I)


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignore=0
        self.items=[]
        self.title_parts=[]
        self.in_h1=False
    def handle_starttag(self,tag,attrs):
        if tag in ("script","style","noscript","template"):
            self.ignore+=1
        if tag=="h1" and not self.ignore:
            self.in_h1=True
    def handle_endtag(self,tag):
        if tag=="h1":
            self.in_h1=False
        if tag in ("script","style","noscript","template") and self.ignore:
            self.ignore-=1
    def handle_data(self,data):
        if self.ignore or not data.strip():
            return
        item=" ".join(data.split())
        self.items.append(item)
        if self.in_h1:
            self.title_parts.append(item)


def parse_detail(raw:bytes,*,expected_url:str,archive_row:dict)->dict:
    """Parse original CAL FIRE incident page, never infer same wildfire identity."""
    if (type(raw) is not bytes or not 0<len(raw)<=MAX_PAGE_BYTES or
            _incident_path(expected_url)!=expected_url or
            archive_row["original_event_url"]!=expected_url):
        raise ValueError("CAL FIRE original detail bytes or archive URL outside pinned contract")
    p=VisibleText()
    p.feed(raw.decode("utf-8-sig"))
    title=" ".join(p.title_parts).strip()
    text=" ".join(p.items)
    if not title or len(title)>250 or "Date Started" not in text:
        raise ValueError("CAL FIRE detail page does not expose expected original incident header/date")
    date=DATE.search(text)
    if date is None:
        raise ValueError("CAL FIRE detail page lacks identifiable source start date")
    # The hour is presented in local/unspecified provider time. Never convert
    # to UTC without a specific provider timezone and original offset.
    source_date=datetime.strptime(date.group(1),"%m/%d/%Y").date().isoformat()
    if source_date[:4]!="2018":
        raise ValueError("CAL FIRE incident detail start-year not 2018")
    title_match=_norm(title)==_norm(archive_row["name"])
    date_match=source_date==archive_row["source_started_at"]
    acres_m=ACRES.search(text[:max(0,text.find("Date Started"))])
    acres=int(acres_m.group(1).replace(",","")) if acres_m else None
    counties=re.search(
        r"\b\d+\s+Count(?:y|ies)\s*:\s*(.{0,180}?)\s+Date Started\b",
        text,re.I)
    source_counties=counties.group(1).strip() if counties else None
    coords=None
    location_excerpt=None
    # Position is source "Location" text, not a calibrated ignition coordinate.
    location=re.search(r"\bLocation\s+(.{0,260}?)\s+Reports\b",text,re.I)
    if location:
        location_excerpt=location.group(1)[:240]
        found=COORD.search(location_excerpt)
        if found:
            lat,lon=float(found.group(1)),float(found.group(2))
            if not(-90<=lat<=90 and -180<=lon<=180):
                raise ValueError("CAL FIRE incident detail location coordinate invalid")
            coords=[lat,lon]
    year_date_mismatch=not date_match or not title_match
    return {
        "source_url":expected_url,
        "source_name":title,
        "archive_name":archive_row["name"],
        "source_started_at":source_date,
        "source_start_clock_local_unspecified_tz":date.group(2),
        "archive_started_at":archive_row["source_started_at"],
        "reported_acres":acres,
        "archive_reported_acres":archive_row["reported_acres"],
        "source_counties":source_counties,
        "archive_counties":archive_row["counties"],
        "source_location_text":location_excerpt,
        "source_location_lat_lon":coords,
        "archive_name_equal_normalized":title_match,
        "archive_start_day_equal":date_match,
        "source_archive_name_or_day_drift":year_date_mismatch,
        "source_page_is_retrospective":True,
        "source_location_is_verified_ignition_point":False,
        "event_identity_verified":False,
        "upstream_independence_verified":False,
    }


def select_leads(archived:dict,max_pages:int,seed:str=SEED,offset:int=0)->list[dict]:
    if type(max_pages) is not int or not 1<=max_pages<=MAX_PAGES:
        raise ValueError("at most 8 incident detail pages per research run")
    if not isinstance(seed,str) or not 1<=len(seed)<=128 or not seed.isascii():
        raise ValueError("source selection seed must be bounded ASCII")
    if type(offset) is not int or not 0<=offset<=1000:
        raise ValueError("source selection offset must be an integer between 0 and 1000")
    by_url={}
    for case in archived["cases"]:
        for lead in case["calfire_name_only_leads"]:
            url=lead["calfire_event_url"]
            if _incident_path(url)!=url:
                raise ValueError("CAL FIRE lead points outside official incident 2018 domain")
            if url not in by_url:
                by_url[url]=[]
            if case["candidate_id"] not in by_url[url]:
                by_url[url].append(case["candidate_id"])
    if not by_url:
        raise ValueError("no original CAL FIRE candidate-linked event page URL available")
    ordered=sorted(by_url,key=lambda u:(hashlib.sha256((seed+":"+u).encode()).hexdigest(),u))
    if offset >= len(ordered):
        raise ValueError("selected page offset is beyond original candidate-linked CAL FIRE URLs")
    return [{
        "source_url":url,"referencing_candidate_ids":sorted(by_url[url])}
        for url in ordered[offset:offset+max_pages]]


def _get(url:str)->bytes:
    if _incident_path(url)!=url:
        raise ValueError("untrusted CAL FIRE destination refused")
    request=Request(url,headers={
        "User-Agent":"WildfireSignals-CALFIRE-Incident-Research/1",
        "Accept":"text/html"})
    with build_opener(_RejectRedirects()).open(request,timeout=30) as response:
        raw=response.read(MAX_PAGE_BYTES+1)
    if len(raw)>MAX_PAGE_BYTES or not raw:
        raise ValueError("CAL FIRE incident original source bytes exceed 2 MiB")
    return raw


def capture(study_dir:Path,archive_dir:Path,*,max_pages:int=4,
            seed:str=SEED,offset:int=0,get=None,clock=None)->tuple[dict,dict[str,bytes]]:
    # The preceding source archive is *replayed* against exact original bytes,
    # not trusted from a possibly edited derived name-lead report.
    archive=replay_archive(study_dir,archive_dir)
    study,digest,cases=load_study(study_dir)
    rows={x["original_event_url"]:x for x in parse_archive(
        (archive_dir/"original-calfire-2018.html").read_bytes())}
    selected=select_leads(archive,max_pages,seed,offset=offset)
    now=clock() if clock else datetime.now(timezone.utc).isoformat()
    captured=datetime.fromisoformat(now.replace("Z","+00:00"))
    if captured.tzinfo is None:
        raise ValueError("capture timestamp must have UTC offset")
    all_cases={case["candidate_id"]:case for case in cases}
    evidence=[]
    raws={}
    records=[]
    for index,selected_row in enumerate(selected,1):
        url=selected_row["source_url"]
        if url not in rows:
            raise ValueError("selected official incident source URL not in authenticated archive")
        raw=(_get(url) if get is None else get(url))
        parsed=parse_detail(raw,expected_url=url,archive_row=rows[url])
        name=f"calfire-original-detail-{index:02d}.html"
        raw_digest=hashlib.sha256(raw).hexdigest()
        raws[name]=raw
        evidence.append({"filename":name,"source_url":url,
                         "sha256":raw_digest,"bytes":len(raw)})
        case_refs=[]
        for cid in selected_row["referencing_candidate_ids"]:
            case=all_cases[cid]
            mtbs_loc=case["mtbs"]
            loc=parsed["source_location_lat_lon"]
            delta=(round(distance_km(loc[0],loc[1],mtbs_loc["latitude"],
                              mtbs_loc["longitude"]),3) if loc else None)
            geo_near=(bool(intersects_circle(
                next(x["geometry"] for x in study["nifc_polygons"]
                     if x["object_id"]==case["nifc"]["object_id"]),
                latitude=loc[0],longitude=loc[1],radius_km=20)) if loc else None)
            # These signals are geographic context, NOT proof that the
            # location is the actual ignition position or same fire.
            case_refs.append({
                "candidate_id":cid,
                "mtbs_source_fire_id":mtbs_loc["fire_id"],
                "nifc_object_id":case["nifc"]["object_id"],
                "mtbs_centroid_to_calfire_location_km":delta,
                "calfire_location_near_nifc_polygon_20km":geo_near,
                "same_event_verified":False,
            })
        records.append({**parsed,"source_file_sha256":raw_digest,
                        "referencing_cases":case_refs})
    report={
        "schema_version":1,
        "status":"original_calfire_detail_source_context_not_verified_event_crosswalk",
        "nifc_mtbs_source_study_sha256":digest,
        "calfire_original_archive_sha256":archive["source_original_html_sha256"],
        "calfire_cross_reference_capture_at":archive["source_capture_at"],
        "details_source_capture_at":captured.astimezone(timezone.utc).isoformat(),
        "selection_seed":seed,
        "max_selected_urls":max_pages,
        "selection_offset":offset,
        "archive_unique_candidate_link_urls":len({
            item["calfire_event_url"]
            for case in archive["cases"] for item in case["calfire_name_only_leads"]}),
        "selected_original_source_urls":selected,
        "selected_page_count":len(records),
        "covers_all_candidate_linked_urls_in_single_batch":(
            offset==0 and len(records)==len({
                item["calfire_event_url"]
                for case in archive["cases"] for item in case["calfire_name_only_leads"]})),
        "pages_with_original_archive_name_or_date_drift":sum(
            x["source_archive_name_or_day_drift"] for x in records),
        "pages_with_reported_location":sum(
            x["source_location_lat_lon"] is not None for x in records),
        "raw_source_files":evidence,
        "pages":records,
        "selected_pages_are_not_all_archive_events":True,
        "event_identity_crosswalks_verified":0,
        "negative_fire_labels_created":0,
        "prediction_skill_measured":False,
        "scientific_limit":(
            "Original CAL FIRE incident detail pages document retrospective name, date, "
            "county and source location, but not independent occurrence corroboration. "
            "Location is NOT proven ignition geometry, and CAL FIRE/NIFC may share inputs. "
            "Selected candidate-linked pages are not a census and unmatched cases are NOT nonfires."),
    }
    if len(json.dumps(report,ensure_ascii=False).encode())>MAX_SUMMARY_BYTES:
        raise ValueError("detail research report exceeds byte budget")
    return report,raws


def save(output:Path,report:dict,raws:dict[str,bytes])->None:
    if output.exists() or output.is_symlink():
        raise ValueError("original detail output must be a new directory")
    output.mkdir(parents=True,mode=0o700)
    try:
        if set(raws)!={x["filename"] for x in report["raw_source_files"]}:
            raise ValueError("source detail byte manifest incomplete")
        for item in report["raw_source_files"]:
            raw=raws[item["filename"]]
            if (len(raw)!=item["bytes"] or len(raw)>MAX_PAGE_BYTES or
                    hashlib.sha256(raw).hexdigest()!=item["sha256"]):
                raise ValueError("source detail page byte hash mismatch")
            with (output/item["filename"]).open("xb") as f:
                f.write(raw)
        with (output/"detail-study.json").open("x",encoding="utf-8") as f:
            json.dump(report,f,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)
            f.write("\n")
    except BaseException:
        for file in output.iterdir():
            if file.is_file():file.unlink()
        output.rmdir()
        raise


def replay(study_dir:Path,archive_dir:Path,output:Path)->dict:
    original=json.loads((output/"detail-study.json").read_text())
    manifest=original["raw_source_files"]
    if len(manifest)>MAX_PAGES:
        raise ValueError("detail archived files exceeded original budget")
    stored={}
    by_url={}
    for item in manifest:
        filename=item["filename"]
        if not re.fullmatch(r"calfire-original-detail-\d{2}\.html",filename):
            raise ValueError("untrusted source evidence filename")
        raw=(output/filename).read_bytes()
        if (not 0<len(raw)<=MAX_PAGE_BYTES or len(raw)!=item["bytes"]
                or hashlib.sha256(raw).hexdigest()!=item["sha256"]):
            raise ValueError("original CAL FIRE detail source bytes SHA-256 mismatch")
        if item["source_url"] in by_url:
            raise ValueError("duplicate archived official source URL")
        by_url[item["source_url"]]=raw
        stored[filename]=raw
    def offline_get(url):
        if url not in by_url:
            raise ValueError("original detail response absent for selected source URL")
        return by_url[url]
    reconstructed,_=capture(
        study_dir,archive_dir,max_pages=original["max_selected_urls"],
        seed=original["selection_seed"],offset=original.get("selection_offset",0),
        get=offline_get,
        clock=lambda:original["details_source_capture_at"])
    # The offline re-evaluation uses injected bytes, but transport is not
    # promoted into trusted new live capture; no transport identity claimed.
    if reconstructed!=original:
        raise ValueError("CAL FIRE original detail source report differs from archived source evidence")
    return reconstructed


def main()->None:
    p=argparse.ArgumentParser(
        description="Actual bounded CAL FIRE original incident detail capture, never verified event match")
    p.add_argument("--study-dir",type=Path,required=True)
    p.add_argument("--calfire-archive-dir",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    p.add_argument("--max-pages",type=int,default=4)
    p.add_argument("--offset",type=int,default=0,
                   help="Zero-based offset in stable hashed CAL FIRE candidate-link order; use batches <=8 pages")
    p.add_argument("--seed",default=SEED)
    args=p.parse_args()
    if (args.output_dir.resolve().is_relative_to(args.study_dir.resolve())
            or args.output_dir.resolve().is_relative_to(args.calfire_archive_dir.resolve())):
        p.error("detail archive output must be outside original provider source archives")
    report,raws=capture(args.study_dir,args.calfire_archive_dir,
                        max_pages=args.max_pages,seed=args.seed,offset=args.offset)
    save(args.output_dir,report,raws)
    replay(args.study_dir,args.calfire_archive_dir,args.output_dir)
    print(json.dumps({
        "status":report["status"],
        "selected_original_incident_pages":report["selected_page_count"],
        "page_offset":report["selection_offset"],
        "total_referenced_unique_incident_urls":report["archive_unique_candidate_link_urls"],
        "pages_with_source_location":report["pages_with_reported_location"],
        "pages_with_archive_metadata_drift":report["pages_with_original_archive_name_or_date_drift"],
        "confirmed_crosswalks":0,"nonfire_labels":0,
    },sort_keys=True))


if __name__=="__main__":
    main()
