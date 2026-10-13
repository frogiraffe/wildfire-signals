"""Source-replayed CAL FIRE alternative-event dossiers for human investigators.

Focuses on candidate cases with multiple plausible *name-based* CAL FIRE
incident-page leads. Historical date/location/record reuse are displayed as
source signals and uncertainty, NEVER classifier scores or true matches.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import date
import hashlib
import html
import io
import csv
import json
import math
from pathlib import Path

from .calfire_incident_archive import _norm
from .calfire_incident_matrix import analyze as replay_full_matrix
from .mtbs_candidate_triage import _csv_safe
from .region_diagnostics import distance_km

MAX_REPORT_BYTES = 2 * 1024 * 1024

CSS = """
:root{font-family:system-ui,sans-serif;color-scheme:light;background:#edf2f5;color:#203943}
body{max-width:1200px;margin:0 auto;padding:18px;line-height:1.5}
header,main,footer{background:white;border:1px solid #c7d2d8;border-radius:10px;padding:20px;margin:14px 0}
h1{font-size:1.7rem}h2{font-size:1.25rem}h3{font-size:1.05rem}
.case{border:1px solid #cedde3;border-radius:8px;margin:12px 0;padding:14px}
.case>summary{font-weight:bold;cursor:pointer}
table{width:100%;border-collapse:collapse;font-size:.9rem}
th,td{border-bottom:1px solid #d4dfe3;padding:8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{background:#edf3f5}
code{overflow-wrap:anywhere}
.warning{color:#80501b}.quiet,small{color:#465e67}
.chip{display:inline-block;border:1px solid #95b0b9;border-radius:5px;padding:3px 7px;margin:2px}
@media(max-width:760px){body{padding:8px}header,main,footer{padding:12px}
thead{display:none}table,tbody,tr,td,th{display:block}tr{border-bottom:2px solid #93a5ad}
td{border:0;padding:5px}td:before{content:attr(data-label) ": ";font-weight:bold}}
"""


def _days(a: object, b: object) -> int | None:
    if not isinstance(a,str) or not isinstance(b,str):
        return None
    try:
        return abs((date.fromisoformat(a[:10])-date.fromisoformat(b[:10])).days)
    except (ValueError,TypeError):
        return None


def build_from_matrix(matrix: dict) -> dict:
    if (matrix.get("research_status") != "full_candidate_link_detail_matrix_not_event_ground_truth"
            or matrix.get("verified_event_crosswalks") != 0
            or matrix.get("verified_nonfire_labels") != 0
            or matrix.get("model_skill_measured") is not False
            or matrix.get("all_candidate_linked_detail_pages_archived") is not True
            or matrix.get("candidate_linked_unique_calfire_urls") !=
                    matrix.get("original_detail_pages_verified")):
        raise ValueError("requires complete, unverified original CAL FIRE candidate-linked matrix")
    cases = matrix.get("cases")
    if not isinstance(cases,list) or len(cases)!=matrix.get("original_candidate_count"):
        raise ValueError("original source cases incomplete")
    degree=Counter()
    for case in cases:
        for lead in case["calfire_leads"]:
            degree[lead["source_url"]]+=1
    if len(degree)!=matrix["candidate_linked_unique_calfire_urls"]:
        raise ValueError("source link population changed while preparing alternative dossiers")

    out=[]
    categories=Counter()
    total_pairwise=0
    candidate_link_reuses=0
    for case in cases:
        cid=case["candidate_id"]
        leads=case["calfire_leads"]
        if len(leads)!=case["calfire_lead_count"]:
            raise ValueError("candidate lead count drift")
        if len({x["source_url"] for x in leads})!=len(leads):
            raise ValueError("candidate contains repeated incident-page URLs")
        if len(leads)>1:
            priority="multiple_original_events_require_identity_investigation"
        elif len(leads)==1:
            priority="single_name_lead_requires_independent_corroboration"
        else:
            priority="no_calfire_name_lead_not_fire_absence"
        categories[priority]+=1
        options=[]
        for lead in leads:
            dist=lead["mtbs_centroid_to_calfire_source_point_km"]
            if dist is not None and (type(dist) not in (int,float) or
                    not math.isfinite(dist) or dist<0):
                raise ValueError("invalid source-point distance")
            if lead["same_fire_verified"] is not False or lead["source_independence_verified"] is not False:
                raise ValueError("source lead cannot assert verified physical wildfire identity")
            repeated=degree[lead["source_url"]]
            if repeated>1:
                candidate_link_reuses+=1
            event_gap=_days(case["mtbs_retrospective_source_day"],lead["source_day"])
            flags=[]
            if lead["archive_name_equal_normalized"] is not True:
                flags.append("calfire_detail_vs_annual_name_drift")
            if lead["archive_date_equal"] is not True:
                flags.append("calfire_detail_vs_annual_start_day_drift")
            if lead["calfire_county_text_check"]!="same_calfire_county_text":
                flags.append("calfire_annual_detail_county_text_missing_or_different")
            if event_gap is None:
                flags.append("mtbs_or_calfire_retrospective_start_day_missing")
            elif event_gap>0:
                flags.append("mtbs_and_calfire_historic_start_days_differ")
            if lead["source_location_lat_lon_not_ignition"] is None:
                flags.append("calfire_source_location_coordinate_missing")
            if repeated>1:
                flags.append("this_calfire_event_url_reused_by_multiple_mtbs_nifc_pairs")
            options.append({
                "source_url":lead["source_url"],
                "source_detail_html_sha256":lead["source_detail_html_sha256"],
                "source_name":lead["source_name"],
                "source_start_day":lead["source_day"],
                "source_local_clock_tz_unspecified":lead["source_clock_local_unspecified_timezone"],
                "source_county_text":lead["source_counties"],
                "source_reported_acres":lead["source_reported_acres"],
                "source_location_lat_lon_not_ignition":lead["source_location_lat_lon_not_ignition"],
                "mtbs_start_day_gap_abs":event_gap,
                "mtbs_centroid_to_source_point_km":dist,
                "source_point_near_nifc_polygon_20km":lead["calfire_source_point_near_nifc_polygon_20km"],
                "source_name_signals":lead["name_signals"],
                "calfire_detail_archive_county_consistency":lead["calfire_county_text_check"],
                "candidate_pair_count_reusing_url":repeated,
                "unresolved_source_signals":flags,
                "verified_event_identity":False,
            })
        options.sort(key=lambda row:row["source_url"])
        pairs=[]
        for idx,left in enumerate(options):
            for right in options[idx+1:]:
                a,b=left["source_location_lat_lon_not_ignition"],right["source_location_lat_lon_not_ignition"]
                separation=(round(distance_km(a[0],a[1],b[0],b[1]),3)
                            if isinstance(a,list) and isinstance(b,list) else None)
                if separation is not None and (not math.isfinite(separation) or separation<0):
                    raise ValueError("invalid separation between original incident page source locations")
                pairs.append({
                    "left_official_incident_url":left["source_url"],
                    "right_official_incident_url":right["source_url"],
                    "different_official_page_urls":left["source_url"]!=right["source_url"],
                    "same_normalized_official_page_name":(
                        _norm(left["source_name"])==_norm(right["source_name"])),
                    "source_start_day_gap_abs":_days(
                        left["source_start_day"],right["source_start_day"]),
                    "displayed_source_point_distance_km_not_ignition":separation,
                    "independent_physical_event_identity_known":False,
                })
        total_pairwise+=len(pairs)
        needs=[
            "inspect_genuine_external_event_records_and_upstream_lineage",
            "human_independent_review_and_documented_source_authentication",
            "independent_event_ID_crosswalk_not_available",
            "comparable_nifc_ignition_day_not_verified",
        ]
        if len(leads)>1:
            needs.append("multiple_official_calfire_incident_pages_must_not_be_auto_collapsed")
        if not leads:
            needs.append("no_calfire_name_lead_is_not_a_nonfire_observation")
        if any(lead["candidate_pair_count_reusing_url"]>1 for lead in options):
            needs.append("shared_calfire_url_across_multiple_source_pairs_requires_group_review")
        out.append({
            "candidate_id":cid,
            "priority_is_manual_work_not_match_probability":True,
            "investigation_priority":priority,
            "mtbs_fire_id":case["mtbs_fire_id"],
            "mtbs_name":case["mtbs_name"],
            "mtbs_fire_type":case["mtbs_fire_type"],
            "mtbs_retrospective_source_day":case["mtbs_retrospective_source_day"],
            "nifc_source_identity":case["nifc_source_identity"],
            "nifc_object_id":case["nifc_object_id"],
            "nifc_name":case["nifc_name"],
            "source_option_count":len(options),
            "official_calfire_page_options":options,
            "alternative_page_pairs":pairs,
            "unresolved_evidence_gates":needs,
            "source_page_context_not_verified_ignition":True,
            "event_identity_verified":False,
            "fire_absence_verified":False,
        })
    out.sort(key=lambda c:(
        0 if c["source_option_count"]>1 else 1 if c["source_option_count"]==1 else 2,
        -c["source_option_count"],c["candidate_id"]))
    result={
        "schema_version":1,
        "research_status":"candidate_alternative_event_dossiers_not_independent_event_identity",
        "nifc_mtbs_original_study_sha256":matrix["study_sha256"],
        "calfire_original_annual_archive_sha256":matrix["annual_calfire_original_html_sha256"],
        "candidate_linked_original_pages_verified":matrix["original_detail_pages_verified"],
        "candidate_linked_unique_pages_verified":matrix["candidate_linked_unique_calfire_urls"],
        "calfire_details_covers_only_name_linked_subset_not_all_historical_fires":True,
        "research_candidate_count":len(out),
        "case_priority_counts":{
            k:categories[k] for k in (
                "multiple_original_events_require_identity_investigation",
                "single_name_lead_requires_independent_corroboration",
                "no_calfire_name_lead_not_fire_absence")},
        "alternative_event_page_pair_comparisons":total_pairwise,
        "candidate_event_url_reuse_occurrences":candidate_link_reuses,
        "cases":out,
        "validated_same_fire_event_crosswalks":0,
        "independent_nonfire_observations":0,
        "measured_wildfire_forecast_skill":False,
        "scientific_limits":[
            "Side-by-side options are NOT predictions of which CAL FIRE event matches MTBS or NIFC.",
            "Name collisions and source event links can reflect one source reporting multiple incident variants.",
            "Multiple candidate pairs citing one CAL FIRE page do NOT constitute independent confirmation.",
            "CAL FIRE location fields are not verified fire ignition points; spatial gap is context only.",
            "MTBS retrospective source date is not assured event decision time; NIFC ignition day is unavailable.",
            "Original CAL FIRE and NIFC may inherit the same upstream agency incident record.",
            "Missing CAL FIRE name leads do not imply nonfire or false wildfire alarms.",
        ],
    }
    if len(json.dumps(result,ensure_ascii=False,allow_nan=False).encode())>MAX_REPORT_BYTES:
        raise ValueError("alternative incident review dossier exceeds output budget")
    return result


def investigate(study_dir:Path,annual_dir:Path,batches:list[Path])->dict:
    # Critical: do not trust any previously written matrix as input.
    # Replay original published bytes and recompute the full cross-source matrix.
    return build_from_matrix(replay_full_matrix(study_dir,annual_dir,batches))


def csv_report(report:dict)->str:
    buf=io.StringIO(newline="")
    writer=csv.writer(buf)
    cols=("candidate_id","investigation_priority","mtbs_fire_id","nifc_source_identity",
          "calfire_original_page_url","calfire_original_page_name",
          "calfire_start_day","mtbs_abs_start_day_gap",
          "calfire_reported_county","mtbs_centroid_to_source_location_km",
          "near_nifc_polygon_20km","shared_page_pair_count","source_sha256",
          "followup_gates")
    writer.writerow(cols)
    for case in report["cases"]:
        for source in case["official_calfire_page_options"] or [None]:
            vals=[
                case["candidate_id"],case["investigation_priority"],
                case["mtbs_fire_id"],case["nifc_source_identity"],
                source["source_url"] if source else None,
                source["source_name"] if source else None,
                source["source_start_day"] if source else None,
                source["mtbs_start_day_gap_abs"] if source else None,
                source["source_county_text"] if source else None,
                source["mtbs_centroid_to_source_point_km"] if source else None,
                source["source_point_near_nifc_polygon_20km"] if source else None,
                source["candidate_pair_count_reusing_url"] if source else None,
                source["source_detail_html_sha256"] if source else None,
                "; ".join(case["unresolved_evidence_gates"]),
            ]
            writer.writerow([_csv_safe(v) for v in vals])
    return buf.getvalue()


def html_report(report:dict)->str:
    if (report.get("research_status")!="candidate_alternative_event_dossiers_not_independent_event_identity"
            or report.get("validated_same_fire_event_crosswalks")!=0
            or report.get("independent_nonfire_observations")!=0):
        raise ValueError("cannot display a fabricated verified event or fire-negative dossier")
    e=lambda value:html.escape(str(value),quote=True)
    blocks=[]
    for case in report["cases"]:
        table_rows=[]
        for option in case["official_calfire_page_options"]:
            attrs=[
                ("Official source", option["source_name"]),
                ("Start day",option["source_start_day"]),
                ("MTBS day gap",option["mtbs_start_day_gap_abs"]),
                ("County",option["source_county_text"]),
                ("MTBS centroid distance km",option["mtbs_centroid_to_source_point_km"]),
                ("Near NIFC polygon (20 km)",option["source_point_near_nifc_polygon_20km"]),
                ("Other case pairs citing same URL",option["candidate_pair_count_reusing_url"]-1),
                ("Source record SHA-256",option["source_detail_html_sha256"]),
                ("Unresolved discrepancies","; ".join(option["unresolved_source_signals"]) or "none"),
            ]
            table_rows.append("<tr><td data-label='Original event page'><a rel='noopener noreferrer' href='"+
                e(option["source_url"])+"'>Official incident page</a></td>"+
                "".join('<td data-label="'+e(k)+'">'+e(v)+"</td>" for k,v in attrs)+"</tr>")
        comparisons=[]
        for pair in case["alternative_page_pairs"]:
            comparisons.append("<li>"+e(pair["left_official_incident_url"])+
                " vs "+e(pair["right_official_incident_url"])+
                "; start-day separation: "+e(pair["source_start_day_gap_abs"])+
                " days; source-location separation: "+
                e(pair["displayed_source_point_distance_km_not_ignition"])+
                " km (NOT actual ignition locations)</li>")
        label=case["candidate_id"]+" · "+str(case["source_option_count"])+" possible official pages"
        content=("<p>MTBS: "+e(case["mtbs_name"])+" / "+e(case["mtbs_fire_id"])+
            "; NIFC: "+e(case["nifc_name"])+
            "; research priority: "+e(case["investigation_priority"])+"</p>")
        if table_rows:
            headings=["Original event page","Official source","Start day","MTBS day gap",
                      "County","MTBS centroid distance km","Near NIFC polygon (20 km)",
                      "Other case pairs citing same URL","Source record SHA-256","Unresolved discrepancies"]
            content+=("<table><thead><tr>"+"".join("<th>"+e(h)+"</th>" for h in headings)+
                "</tr></thead><tbody>"+"".join(table_rows)+"</tbody></table>")
        else:
            content+="<p>There is no CAL FIRE name lead. This is NOT evidence of no wildfire.</p>"
        if comparisons:
            content+="<h3>Differences between candidate official incident pages</h3><ul>"+\
                "".join(comparisons)+"</ul>"
        content+="<p>Required evidence: "+e("; ".join(case["unresolved_evidence_gates"]))+"</p>"
        blocks.append('<details class="case" open><summary>'+e(label)+"</summary>"+content+"</details>")
    css=base64.b64encode(hashlib.sha256(CSS.encode()).digest()).decode()
    csp=("default-src 'none'; script-src 'none'; connect-src 'none'; img-src 'none'; "
         "object-src 'none'; base-uri 'none'; style-src 'sha256-"+css+"'")
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="'+e(csp)+'">'
        '<title>Original CAL FIRE alternatives – research only</title><style>'+CSS+
        '</style></head><body><header><h1>CAL FIRE historical alternative-event dossiers</h1>'
        '<p>Original NIFC/MTBS study SHA-256: '+e(report["nifc_mtbs_original_study_sha256"])+'</p>'
        '<p>All candidate-linked original pages archived: '+str(report["candidate_linked_unique_pages_verified"])+
        '</p><p class="warning">These are historical source comparisons for manual investigation, '
        'not independent physical fire-event matches or validated nonfire observations.</p></header>'
        '<main>'+"".join(blocks)+'</main><footer>'
        '<p>Verified event identities: 0 · Independent nonfire cases: 0 · Forecast skill: not measured.</p>'
        '</footer></body></html>\n')


def export(report:dict,destination:Path,*,study_dir:Path,annual_dir:Path,batches:list[Path])->None:
    original_paths=[study_dir.resolve(),annual_dir.resolve()]+[x.resolve() for x in batches]
    if (destination.is_symlink() or destination.exists() or
            any(destination.resolve().is_relative_to(root) or
                root.is_relative_to(destination.resolve()) for root in original_paths)):
        raise ValueError("new dossier output directory must not contain or overlap original source archives")
    result_files={
        "ambiguity-dossiers.json":json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+"\n",
        "ambiguity-dossiers.csv":csv_report(report),
        "ambiguity-dossiers.html":html_report(report),
    }
    if any(len(s.encode())>MAX_REPORT_BYTES for s in result_files.values()):
        raise ValueError("dossier format exceeded original research output budget")
    destination.mkdir(parents=True,mode=0o700)
    try:
        for name,data in result_files.items():
            with (destination/name).open("x",encoding="utf-8") as handle:
                handle.write(data)
    except BaseException:
        for child in destination.iterdir():
            if child.is_file():child.unlink()
        destination.rmdir()
        raise


def main()->None:
    cli=argparse.ArgumentParser(description="Original source SHA-backed ambiguous CAL FIRE alternative-event dossier, NOT ground truth")
    cli.add_argument("--study-dir",type=Path,required=True)
    cli.add_argument("--calfire-archive-dir",type=Path,required=True)
    cli.add_argument("--batch",type=Path,action="append",required=True)
    cli.add_argument("--output-dir",type=Path,required=True)
    args=cli.parse_args()
    result=investigate(args.study_dir,args.calfire_archive_dir,args.batch)
    export(result,args.output_dir,study_dir=args.study_dir,
           annual_dir=args.calfire_archive_dir,batches=args.batch)
    print(json.dumps({
        "cases":result["research_candidate_count"],
        "original_calfire_pages_replayed":result["candidate_linked_unique_pages_verified"],
        "research_categories":result["case_priority_counts"],
        "alternative_page_comparisons":result["alternative_event_page_pair_comparisons"],
        "verified_same_fire_crosswalks":0,"verified_nonfire":0,
    },sort_keys=True))


if __name__=="__main__":
    main()
