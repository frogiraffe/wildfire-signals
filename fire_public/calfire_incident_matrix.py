"""Source-verified complete CAL FIRE candidate-page coverage and review matrix.

Combines bounded 2018 CAL FIRE detail batches, replays every original HTTP
response, and enumerates signals for *human investigation only*. No verified
same-fire crosswalk, predicted fire/nonfire, or calibrated skill inference.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import html
import json
import math
from pathlib import Path

from .calfire_incident_archive import replay as replay_archive
from .calfire_incident_details import replay as replay_batch
from .mtbs_match_review import load_study
from .mtbs_candidate_triage import _csv_safe
import csv
import io

MAX_DETAIL_BATCHES = 12
MAX_CANDIDATE_LINKS = 64
MAX_REPORT_BYTES = 2*1024*1024

STYLE = """
:root{font-family:system-ui,sans-serif;background:#f2f6f7;color:#193440;color-scheme:light}
body{max-width:1240px;margin:0 auto;padding:16px;line-height:1.5}
header,main,footer{background:white;border:1px solid #c9d7db;border-radius:10px;padding:18px;margin:12px 0}
h1{font-size:1.6rem}h2{font-size:1.18rem}h3{font-size:1rem}
table{border-collapse:collapse;width:100%;font-size:.93rem}
th,td{border-bottom:1px solid #cbd9df;padding:9px;text-align:left;vertical-align:top}
th{background:#edf3f5}td{overflow-wrap:anywhere}
small{color:#516975}.warning{color:#82511b}code{overflow-wrap:anywhere}
summary{cursor:pointer;font-weight:600}
@media(max-width:760px){body{padding:8px}header,main,footer{padding:12px}
table,thead,tbody,tr,td,th{display:block}thead{display:none}
tr{border-bottom:2px solid #7a9eaa}td{border:0;padding:5px}
td:before{content:attr(data-label) ": ";font-weight:700}}
"""


def analyze(study_dir:Path,archive_dir:Path,batches:list[Path])->dict:
    if not isinstance(batches,list) or not 1<=len(batches)<=MAX_DETAIL_BATCHES:
        raise ValueError("1..12 distinct original detail batch directories required")
    resolved={p.resolve() for p in batches}
    if (len(resolved)!=len(batches) or
            any(p.resolve().is_relative_to(study_dir.resolve()) or
                p.resolve().is_relative_to(archive_dir.resolve()) for p in batches)):
        raise ValueError("detail batch directories must be distinct and outside original source archives")
    archived=replay_archive(study_dir,archive_dir)
    study,digest,cases=load_study(study_dir)
    if (study["year"]!=2018 or archived["nifc_mtbs_source_study_sha256"]!=digest
            or archived["confirmed_event_identity_count"]!=0):
        raise ValueError("CAL FIRE region study/original source crosswalk contract incompatible")
    all_links={
        lead["calfire_event_url"] for case in archived["cases"]
        for lead in case["calfire_name_only_leads"]
    }
    if not 1<=len(all_links)<=MAX_CANDIDATE_LINKS:
        raise ValueError("unsupported full CAL FIRE candidate link population")
    page_map={}
    source_evidence=[]
    slices=[]
    seeds=set()
    for path in batches:
        report=replay_batch(study_dir,archive_dir,path)
        if (report["nifc_mtbs_source_study_sha256"]!=digest or
                report["calfire_original_archive_sha256"]!=archived["source_original_html_sha256"] or
                report["event_identity_crosswalks_verified"]!=0 or
                report["negative_fire_labels_created"]!=0):
            raise ValueError("source detail batch links different or verified original source claims")
        seeds.add(report["selection_seed"])
        start=report["selection_offset"]
        end=start+report["selected_page_count"]
        slices.append([start,end])
        for page,evidence in zip(report["pages"],report["raw_source_files"]):
            url=page["source_url"]
            if (url in page_map or url not in all_links or
                    page["source_file_sha256"]!=evidence["sha256"] or
                    url!=evidence["source_url"]):
                raise ValueError("duplicate, unexpected or unverified CAL FIRE original detail source page")
            page_map[url]=page
            source_evidence.append({
                "source_url":url,"detail_html_sha256":evidence["sha256"],
                "original_bytes":evidence["bytes"],
                "research_batch_directory":path.name,
                "original_filename":evidence["filename"],
            })
    if len(seeds)!=1:
        raise ValueError("detail batches use different deterministic source URL selection seeds")
    if set(page_map)!=all_links:
        missing=sorted(all_links-set(page_map))
        raise ValueError(f"CAL FIRE detail page coverage incomplete; missing {len(missing)} original links")
    # The bounded fetch selection indices must form an unbroken partition,
    # not just happen to contain all links after accidental shifting.
    segments=sorted(slices)
    cursor=0
    for start,end in segments:
        if start!=cursor or end<=start:
            raise ValueError("original detail batch offsets overlap or skip source URL order")
        cursor=end
    if cursor!=len(all_links):
        raise ValueError("original candidate-linked source URL count disagrees with batch selection")
    annual_cases={x["candidate_id"]:x for x in archived["cases"]}
    if {x["candidate_id"] for x in cases}!=set(annual_cases):
        raise ValueError("annual event candidates do not correspond to original geometry study")
    rows=[]
    stats=Counter()
    for case in cases:
        cid=case["candidate_id"]
        annual=annual_cases[cid]
        details=[]
        for lead in annual["calfire_name_only_leads"]:
            url=lead["calfire_event_url"]
            original=page_map[url]
            reference=next((item for item in original["referencing_cases"]
                            if item["candidate_id"]==cid),None)
            if reference is None or reference["same_event_verified"] is not False:
                raise ValueError("detail source page omitted original candidate context")
            mtbs=case["mtbs"]
            mtbs_day=mtbs["source_ignition_at"][:10] if mtbs["source_ignition_at"] else None
            cal_day=original["source_started_at"]
            if mtbs_day is None or cal_day is None:
                temporal="retrospective_date_not_comparable"
            else:
                temporal=("retrospective_same_calendar_day" if mtbs_day==cal_day
                          else "retrospective_different_calendar_day")
            ac=original["archive_counties"]
            pc=original["source_counties"]
            if not isinstance(ac,str) or not ac.strip() or not isinstance(pc,str) or not pc.strip():
                county="one_or_both_calfire_county_fields_missing"
            else:
                from .calfire_incident_archive import _norm
                county=("same_calfire_county_text" if _norm(ac)==_norm(pc)
                        else "different_calfire_county_text_not_geo_validation")
            distance=reference["mtbs_centroid_to_calfire_location_km"]
            near=reference["calfire_location_near_nifc_polygon_20km"]
            if distance is not None and (type(distance) not in (float,int) or
                     not math.isfinite(distance) or distance<0):
                raise ValueError("unbounded MTBS-to-CAL FIRE descriptive source distance")
            if near not in (None,False,True):
                raise ValueError("original NIFC source proximity value invalid")
            details.append({
                "source_url":url,
                "source_detail_html_sha256":original["source_file_sha256"],
                "archive_row_ordinal":lead["archive_row_ordinal"],
                "source_name":original["source_name"],
                "source_day":cal_day,
                "source_clock_local_unspecified_timezone":original["source_start_clock_local_unspecified_tz"],
                "source_counties":pc,
                "source_location_lat_lon_not_ignition":original["source_location_lat_lon"],
                "source_reported_acres":original["reported_acres"],
                "archive_name_equal_normalized":original["archive_name_equal_normalized"],
                "archive_date_equal":original["archive_start_day_equal"],
                "calfire_county_text_check":county,
                "mtbs_calfire_retrospective_date_check":temporal,
                "mtbs_centroid_to_calfire_source_point_km":distance,
                "calfire_source_point_near_nifc_polygon_20km":near,
                "name_signals":lead["name_signals"],
                "same_fire_verified":False,
                "source_independence_verified":False,
            })
            stats[temporal]+=1
        details.sort(key=lambda item:item["source_url"])
        if not details:
            status="no_calfire_name_lead_not_fire_absence"
        elif len(details)>1:
            status="multiple_calfire_events_need_disambiguation"
        else:
            status="single_calfire_name_lead_requires_review"
        stats[status]+=1
        rows.append({
            "candidate_id":cid,
            "mtbs_fire_id":case["mtbs"]["fire_id"],
            "mtbs_name":case["mtbs"]["name"],
            "mtbs_fire_type":case["mtbs"]["fire_type"],
            "mtbs_retrospective_source_day":(
                case["mtbs"]["source_ignition_at"][:10] if case["mtbs"]["source_ignition_at"] else None),
            "nifc_object_id":case["nifc"]["object_id"],
            "nifc_source_identity":case["nifc"]["source_identity"],
            "nifc_name":case["nifc"]["name"],
            "nifc_ignition_day_verified":False,
            "calfire_leads":details,
            "calfire_lead_count":len(details),
            "work_status":status,
            "missing_name_lead_is_not_nonfire":True,
            "verified_same_fire_event":False,
        })
    rows.sort(key=lambda x:x["candidate_id"])
    result={
        "schema_version":1,
        "research_status":"full_candidate_link_detail_matrix_not_event_ground_truth",
        "study_sha256":digest,
        "annual_calfire_original_html_sha256":archived["source_original_html_sha256"],
        "calfire_2018_archive_row_count":archived["calfire_archive_records_parsed"],
        "original_candidate_count":len(cases),
        "candidate_linked_unique_calfire_urls":len(all_links),
        "original_detail_pages_verified":len(page_map),
        "all_candidate_linked_detail_pages_archived":True,
        "candidate_detail_links_are_not_complete_calfire_fire_census":True,
        "selection_seed":next(iter(seeds)),
        "original_detail_page_batch_count":len(batches),
        "selected_source_evidence_files":sorted(source_evidence,key=lambda x:x["source_url"]),
        "candidate_outcomes":{
            k:stats[k] for k in ("no_calfire_name_lead_not_fire_absence",
                                 "multiple_calfire_events_need_disambiguation",
                                 "single_calfire_name_lead_requires_review")},
        "retrospective_date_comparisons":{
            k:stats[k] for k in ("retrospective_same_calendar_day",
                                 "retrospective_different_calendar_day",
                                 "retrospective_date_not_comparable")},
        "cases":rows,
        "verified_event_crosswalks":0,
        "verified_nonfire_labels":0,
        "model_skill_measured":False,
        "limits":[
            "All CAL FIRE candidate-linked incident pages are archived; most 2018 fire events are not in this name-linked subset.",
            "Same names, dates, county text or near points are descriptive retrospective clues, not fire identity proof.",
            "CAL FIRE point source locations are not verified ignition locations and may lack reliable precision.",
            "Original NIFC fire year is not a verified ignition day; MTBS original date fields may be retrospective.",
            "CAL FIRE and NIFC may share upstream reports, so a third source does not establish independent occurrence validation.",
            "No CAL FIRE name candidate or detail page is never evidence of wildfire absence.",
        ],
    }
    if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>MAX_REPORT_BYTES:
        raise ValueError("retrospective research matrix exceeds byte budget")
    return result


def as_csv(report:dict)->str:
    out=io.StringIO(newline="")
    writer=csv.writer(out)
    cols=("candidate_id","work_status","mtbs_fire_id","mtbs_name","nifc_source_identity",
          "nifc_name","calfire_url","calfire_name","calfire_source_day",
          "mtbs_calfire_retrospective_date_check","calfire_county_text_check",
          "distance_km","near_nifc_polygon_20km","source_sha256")
    writer.writerow(cols)
    for case in report["cases"]:
        for lead in case["calfire_leads"] or [None]:
            values=(
                case["candidate_id"],case["work_status"],case["mtbs_fire_id"],
                case["mtbs_name"],case["nifc_source_identity"],case["nifc_name"],
                lead["source_url"] if lead else None,
                lead["source_name"] if lead else None,
                lead["source_day"] if lead else None,
                lead["mtbs_calfire_retrospective_date_check"] if lead else None,
                lead["calfire_county_text_check"] if lead else None,
                lead["mtbs_centroid_to_calfire_source_point_km"] if lead else None,
                lead["calfire_source_point_near_nifc_polygon_20km"] if lead else None,
                lead["source_detail_html_sha256"] if lead else None,
            )
            writer.writerow([_csv_safe(x) for x in values])
    return out.getvalue()


def as_html(report:dict)->str:
    if (report.get("research_status")!="full_candidate_link_detail_matrix_not_event_ground_truth"
            or report.get("verified_event_crosswalks")!=0
            or report.get("verified_nonfire_labels")!=0):
        raise ValueError("only scientifically guarded source matrix can be rendered")
    e=lambda value:html.escape(str(value),quote=True)
    rows=[]
    for case in report["cases"]:
        lead_items=[]
        for lead in case["calfire_leads"]:
            columns=(
                ("CAL FIRE event",lead["source_name"]),
                ("Original start day",lead["source_day"]),
                ("MTBS day comparison",lead["mtbs_calfire_retrospective_date_check"]),
                ("CAL FIRE county text check",lead["calfire_county_text_check"]),
                ("MTBS distance (km)",lead["mtbs_centroid_to_calfire_source_point_km"]),
                ("Near NIFC polygon (20 km)",lead["calfire_source_point_near_nifc_polygon_20km"]),
                ("Original HTML SHA-256",lead["source_detail_html_sha256"]),
            )
            details="; ".join(f"{key}: {value}" for key,value in columns)
            lead_items.append("<li>"+e(details)+"; <a href='"+e(lead["source_url"])+
                             "' rel='noreferrer noopener'>Official incident page</a></li>")
        if not lead_items:
            lead_items=["<li>No CAL FIRE name lead; NOT an observation of no wildfire</li>"]
        cards="<details><summary>"+str(case["calfire_lead_count"])+\
            " original incident lead(s)</summary><ul>"+"".join(lead_items)+"</ul></details>"
        vals=[
            ("Candidate",case["candidate_id"]),
            ("MTBS",case["mtbs_name"]+" / "+case["mtbs_fire_id"]),
            ("NIFC",case["nifc_name"]),
            ("Research state",case["work_status"]),
        ]
        rows.append("<tr>"+"".join(
            '<td data-label="'+e(name)+'">'+e(value)+"</td>" for name,value in vals
        )+'<td data-label="CAL FIRE details">'+cards+"</td></tr>")
    css_hash=base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    csp=("default-src 'none'; script-src 'none'; connect-src 'none'; img-src 'none'; "
         "object-src 'none'; base-uri 'none'; style-src 'sha256-"+css_hash+"'")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="'+e(csp)+'">'
            '<title>Retrospective CAL FIRE incident investigation matrix</title>'
            '<style>'+STYLE+'</style></head><body><header>'
            '<h1>CAL FIRE · NIFC · MTBS retrospective candidate matrix</h1>'
            '<p>Verified source study SHA-256: <code>'+e(report["study_sha256"])+'</code></p>'
            '<p>Candidate-linked pages archived: '+str(report["original_detail_pages_verified"])+
            ' / '+str(report["candidate_linked_unique_calfire_urls"])+'</p>'
            '<p class="warning">All event relations here are investigation clues, '
            'not verified identities or negative cases. CAL FIRE and NIFC may share source records.'
            '</p></header><main><table><thead><tr>'+''.join(
              '<th>'+e(t)+'</th>' for t in
              ("Candidate","MTBS","NIFC","Research state","CAL FIRE details"))+
            '</tr></thead><tbody>'+''.join(rows)+'</tbody></table></main>'
            '<footer>Full candidate-linked URL coverage does not imply complete regional fire coverage.'
            ' Verified identities: 0 · Independent wildfire negatives: 0</footer>'
            '</body></html>\n')


def write_reports(report:dict,json_file:Path,csv_file:Path,html_file:Path,
                  *,study_dir:Path,archive_dir:Path,batches:list[Path])->None:
    outputs=[json_file,csv_file,html_file]
    originals=[study_dir.resolve(),archive_dir.resolve()]+[p.resolve() for p in batches]
    if (len({p.resolve() for p in outputs})!=3 or
            any(p.exists() or p.is_symlink() or any(p.resolve().is_relative_to(root)
                        for root in originals) for p in outputs)):
        raise ValueError("outputs must be new, distinct and outside original government source batches")
    serialized=(
        (json_file,json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+"\n"),
        (csv_file,as_csv(report)),
        (html_file,as_html(report)),
    )
    if any(len(s.encode())>MAX_REPORT_BYTES for _,s in serialized):
        raise ValueError("matrix output exceeds report byte budget")
    created=[]
    try:
        for filename,data in serialized:
            filename.parent.mkdir(parents=True,exist_ok=True)
            with filename.open("x",encoding="utf-8") as stream:
                stream.write(data)
            created.append(filename)
    except BaseException:
        for filename in created:
            filename.unlink()
        raise


def main()->None:
    p=argparse.ArgumentParser(description="Replayed full CAL FIRE candidate-linked original page matrix, NOT wildfire ground truth")
    p.add_argument("--study-dir",type=Path,required=True)
    p.add_argument("--calfire-archive-dir",type=Path,required=True)
    p.add_argument("--batch",type=Path,action="append",required=True,
                   help="One original CAL FIRE <=8-page detail source evidence directory; repeat for all URL offsets")
    p.add_argument("--json",type=Path,required=True)
    p.add_argument("--csv",type=Path,required=True)
    p.add_argument("--html",type=Path,required=True)
    args=p.parse_args()
    report=analyze(args.study_dir,args.calfire_archive_dir,args.batch)
    write_reports(report,args.json,args.csv,args.html,study_dir=args.study_dir,
                  archive_dir=args.calfire_archive_dir,batches=args.batch)
    print(json.dumps({
        "source_candidate_cases":report["original_candidate_count"],
        "authentic_original_detail_urls":report["original_detail_pages_verified"],
        "full_original_candidate_link_coverage":report["all_candidate_linked_detail_pages_archived"],
        "case_dispositions":report["candidate_outcomes"],
        "verified_fire_event_crosswalks":0,"verified_nonfire_labels":0
    },sort_keys=True))


if __name__=="__main__":
    main()
