"""Offline manual MTBS–NIFC proximity review with source-byte audit.

Creates an isolated static HTML research packet from a real two-provider
shared-ROI archive; never turns opinions into binary wildfire labels.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import math
import re
from pathlib import Path
from urllib.parse import urlsplit

from .label_review import _text
from .mtbs_pilot import _first_by_hash
from .official_perimeters import _canonical
from .mtbs_pilot import _parse_feature, BASE, YEARS
from .official_perimeters import SERVICE, _feature, intersects_circle

MAX_RAW_BYTES = 8 * 1024 * 1024
MAX_REPORT_BYTES = 12 * 1024 * 1024
MAX_VOTES_BYTES = 300 * 1024
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DECISIONS = {"same_event_hypothesis", "different_event_hypothesis", "inconclusive"}

STYLE = """
:root{font-family:system-ui,sans-serif;color-scheme:light;background:#eef2f4;color:#182e37}
body{max-width:1140px;margin:0 auto;padding:20px;line-height:1.5}
header,main,footer{background:white;border:1px solid #cbd6da;border-radius:12px;
padding:20px;margin:14px 0}
h1{font-size:1.65rem}h2{font-size:1.2rem}
.notice{color:#7b4a11}.quiet{color:#48616e}
article{padding:14px;border:1px solid #cbd6da;border-radius:9px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
label{display:block;font-weight:600;margin:12px 0}
input,textarea,select{box-sizing:border-box;display:block;width:100%;padding:10px;
border:1px solid #7c959d;border-radius:5px;font-size:1rem}
textarea{min-height:100px;resize:vertical}
button{background:#164e62;border:0;border-radius:7px;padding:11px 18px;
font-weight:600;color:white;cursor:pointer}
button:disabled{background:#9baaad;cursor:default}
button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{
outline:3px solid #b76f31;outline-offset:2px}
nav{display:flex;gap:12px;align-items:center;margin:18px 0}
#review-map{width:100%;height:310px;background:#f3f6f7;border:1px solid #cbd6da;
border-radius:6px}
#errors{white-space:pre-wrap;color:#9c2730}
svg .fire-shape{fill:#e6a37666;stroke:#a04e22;stroke-width:2}
svg .mtbs-point{fill:#176d83;stroke:white;stroke-width:2}
small{color:#415763}.hidden{display:none}
@media(max-width:680px){body{padding:8px}header,main,footer{padding:12px}
.grid{grid-template-columns:1fr}nav{flex-wrap:wrap}#review-map{height:250px}}
"""

SCRIPT = r"""
'use strict';
const bytes = Uint8Array.from(atob('PAYLOAD_BASE64'), c => c.charCodeAt(0));
const model = JSON.parse(new TextDecoder('utf-8').decode(bytes));
const cases = model.cases;
const choices = ['unreviewed','same_event_hypothesis',
                 'different_event_hypothesis','inconclusive'];
let index = 0;
const drafts = cases.map(() => ({decision:'unreviewed', reason:'', evidence_url:''}));
const $ = id => document.getElementById(id);
$('study').textContent = model.year + ' · ' + model.region.join(', ') +
  ' · ' + cases.length + ' proximity candidates';
$('reviewer').textContent = model.reviewer_id;
$('digest').textContent = model.source_bundle_sha256;
const svgNS = 'http://www.w3.org/2000/svg';
function svgElement(tag, attrs) {
  const el = document.createElementNS(svgNS,tag);
  for (const [key,value] of Object.entries(attrs)) el.setAttribute(key,String(value));
  return el;
}
function renderGeometry(c) {
  const svg=$('review-map');
  svg.replaceChildren();
  svg.setAttribute('role','img');
  svg.setAttribute('aria-label','Approximate MTBS point and NIFC polygon geometry preview; not an accurate GIS map');
  const points = c.preview_rings.flat().concat([[c.mtbs.longitude,c.mtbs.latitude]]);
  const x=points.map(p=>p[0]), y=points.map(p=>p[1]);
  const minx=Math.min(...x),maxx=Math.max(...x),miny=Math.min(...y),maxy=Math.max(...y);
  const midLat=(miny+maxy)/2*Math.PI/180;
  const stretch=Math.max(.02,Math.cos(midLat));
  const width=Math.max(.000001,(maxx-minx)*stretch);
  const height=Math.max(.000001,maxy-miny);
  const pad=.12, w=700,h=300;
  const fit=Math.min((w*(1-2*pad))/width,(h*(1-2*pad))/height);
  const offsetX=(w-width*fit)/2,offsetY=(h-height*fit)/2;
  const toXY=p=>[offsetX+(p[0]-minx)*stretch*fit,
    h-offsetY-(p[1]-miny)*fit];
  svg.setAttribute('viewBox','0 0 700 300');
  for (const ring of c.preview_rings) {
    if(ring.length<3) continue;
    const path = ring.map((p,i)=>{
      const [xx,yy]=toXY(p);
      return (i===0?'M':'L')+xx.toFixed(2)+' '+yy.toFixed(2);
    }).join(' ')+' Z';
    svg.append(svgElement('path',{d:path,class:'fire-shape'}));
  }
  const [px,py]=toXY([c.mtbs.longitude,c.mtbs.latitude]);
  svg.append(svgElement('circle',{cx:px,cy:py,r:7,class:'mtbs-point'}));
}
function save() {
  const d=drafts[index];
  d.decision=$('decision').value;
  d.reason=$('reason').value;
  d.evidence_url=$('evidence').value;
}
function render() {
  const c=cases[index], d=drafts[index];
  $('position').textContent='Candidate '+(index+1)+' of '+cases.length;
  $('nifc').textContent='NIFC perimeter #'+c.nifc.object_id+' · '+
    (c.nifc.name||'(unnamed)')+' · reported '+c.nifc.reported_acres+' acres';
  $('mtbs').textContent='MTBS #'+c.mtbs.object_id+' · '+
    (c.mtbs.name||'(unnamed)')+' · '+(c.mtbs.fire_type||'type unknown')+
    ' · reported '+c.mtbs.reported_acres+' acres';
  $('date').textContent='MTBS source date: '+(c.mtbs.source_ignition_at||'unavailable')+
    ' (retrospective attribute, not historical decision-time evidence)';
  $('identity').textContent='MTBS fire ID '+c.mtbs.fire_id+
    ' · NIFC identity '+c.nifc.source_identity;
  $('decision').value=d.decision;
  $('reason').value=d.reason;
  $('evidence').value=d.evidence_url;
  $('prev').disabled=index===0;
  $('next').disabled=index===cases.length-1;
  $('progress').textContent='Explicitly reviewed '+drafts.filter(x=>x.decision!=='unreviewed').length+
    ' / '+cases.length;
  renderGeometry(c);
}
$('prev').addEventListener('click',()=>{save();index--;render();});
$('next').addEventListener('click',()=>{save();index++;render();});
function validHttps(value) {
  try {let u=new URL(value);return u.protocol==='https:'&&Boolean(u.hostname);}
  catch(_){return false;}
}
$('export').addEventListener('click',()=>{
  save();
  const errors=[];
  const votes=cases.map((c,i)=>{
    const d=drafts[i], decision=d.decision, reason=d.reason.trim();
    const link=d.evidence_url.trim();
    if(!choices.includes(decision)||decision==='unreviewed')
      errors.push('Candidate '+(i+1)+': explicitly choose a review disposition.');
    if(reason.length<15)
      errors.push('Candidate '+(i+1)+': enter a reason (15 or more characters).');
    if(decision!=='inconclusive' && !validHttps(link))
      errors.push('Candidate '+(i+1)+': an HTTPS independent evidence URL is required for a hypothesis.');
    if(link && !validHttps(link))
      errors.push('Candidate '+(i+1)+': evidence URL must be HTTPS.');
    return {candidate_id:c.candidate_id,decision,reason,
      evidence_url:link||null};
  });
  $('errors').textContent=errors.join('\n');
  if(errors.length) {
    $('status').textContent='No review exported. Correct the listed fields.';
    return;
  }
  const output={
    schema_version:1,source_bundle_sha256:model.source_bundle_sha256,
    reviewer_id:model.reviewer_id,reviewed_at:new Date().toISOString(),
    classifications_are_unverified_hypotheses:true,votes
  };
  const blob=new Blob([JSON.stringify(output,null,2)+'\n'],{type:'application/json'});
  const link=URL.createObjectURL(blob),a=document.createElement('a');
  a.href=link;a.download='mtbs-nifc-pair-review-'+model.reviewer_id.replace(/[^A-Z0-9_-]/gi,'_')+'.json';
  document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(link),3000);
  $('status').textContent='Local hypothesis review downloaded. No outcomes or fire-negative labels created.';
});
render();
"""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bounded_file(path: Path, max_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= max_bytes:
        raise ValueError(f"source file missing, symlink or too large: {path.name}")
    return path.read_bytes()


def _name(path: str) -> bool:
    return (bool(re.fullmatch(r"(?:nifc|mtbs)-20(?:17|18)-[a-z0-9-]+\.(?:json|geojson)",path))
            and "/" not in path and ".." not in path)


def _preview(geometry: dict) -> list[list[list[float]]]:
    from .official_perimeters import _rings
    rings = _rings(geometry)
    # Preview only: deterministic, intentionally simplified to prevent a huge
    # browser payload; NEVER used for geometric matching or research metrics.
    output=[]
    for ring in rings[:12]:
        step=max(1,math.ceil(len(ring)/550))
        reduced=ring[::step]
        if reduced[-1]!=ring[-1]:
            reduced.append(ring[-1])
        output.append([[float(p[0]),float(p[1])] for p in reduced])
    return output


def load_study(folder: Path) -> tuple[dict, str, list[dict]]:
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("existing study directory required")
    report_bytes=_bounded_file(folder/"aligned-study.json",MAX_REPORT_BYTES)
    report=json.loads(report_bytes)
    if (report.get("schema_version")!=1 or report.get("year") not in YEARS or
            report.get("nifc_source")!=SERVICE or
            report.get("mtbs_source")!=f"{BASE}/{YEARS[report['year']]}" or
            report.get("same_fire_event_identifications_verified")!=0 or
            report.get("negative_labels_created")!=0 or
            report.get("forecast_model_skill_measured") is not False):
        raise ValueError("unsupported or scientifically misrepresented aligned source study")
    year=report["year"]
    nifc=report.get("nifc_polygons")
    mtbs=report.get("mtbs_points")
    pairs=report.get("candidate_pairs")
    if (not isinstance(nifc,list) or not isinstance(mtbs,list) or
            not isinstance(pairs,list) or len(nifc)>40 or len(mtbs)>40 or
            len(pairs)>1600):
        raise ValueError("aligned source study record budget or arrays invalid")
    entries=report.get("raw_source_files")
    if not isinstance(entries,list) or not 3<=len(entries)<=10:
        raise ValueError("original source byte descriptors missing")
    raws={}
    for meta in entries:
        if not isinstance(meta,dict) or not _name(meta.get("filename","")):
            raise ValueError("unsafe original provider response filename")
        name=meta["filename"]
        if name in raws:
            raise ValueError("duplicate source response filename")
        raw=_bounded_file(folder/name,MAX_RAW_BYTES)
        if (meta.get("bytes")!=len(raw) or
                not isinstance(meta.get("sha256"),str) or
                not HEX64.fullmatch(meta["sha256"]) or
                _sha(raw)!=meta["sha256"]):
            raise ValueError("original source response SHA-256 or byte length mismatch")
        raws[name]=raw
    # Recompute government-published ROI ObjectID populations and the seeded
    # deterministic selection, not merely the previously formatted report.
    populations=report.get("source_population")
    if not isinstance(populations,dict):
        raise ValueError("source population metadata required")
    expected_selected={}
    for provider in ("nifc","mtbs"):
        id_name=f"{provider}-{year}-roi-ids.json"
        if id_name not in raws:
            raise ValueError("original regional source IDs unavailable")
        ids=json.loads(raws[id_name]).get("objectIds")
        if (not isinstance(ids,list) or not ids or len(ids)>50000 or
                len(set(ids))!=len(ids) or
                any(type(x) is not int or x<0 for x in ids)):
            raise ValueError("invalid or censored ROI source ID population")
        ids=sorted(ids)
        sample=_first_by_hash(ids,year,
            min(len(ids),report["record_limit_per_source"]),
            provider+":"+report["selected_id_seed"])
        if (populations.get(provider+"_roi_object_ids")!=len(ids) or
                populations.get(provider+"_roi_ids_sha256")!=
                     hashlib.sha256(_canonical(ids).encode()).hexdigest() or
                populations.get(provider+"_selected_ids_sha256")!=
                     hashlib.sha256(_canonical(sample).encode()).hexdigest()):
            raise ValueError("declared source ROI population/selection differs from original response")
        expected_selected[provider]=set(sample)
    if populations.get("both_selected_records_exhaust_all_source_roi_ids") is not (
        len(expected_selected["nifc"])==populations["nifc_roi_object_ids"] and
        len(expected_selected["mtbs"])==populations["mtbs_roi_object_ids"]):
        raise ValueError("source record sample-completeness flag inconsistent")
    nifc_orig={}
    for name,raw in raws.items():
        if name.startswith(f"nifc-{year}-page-"):
            page=json.loads(raw)
            if page.get("type")!="FeatureCollection" or not isinstance(page.get("features"),list):
                raise ValueError("NIFC provider shape invalid")
            for feature in page["features"]:
                p=feature.get("properties") or {}
                oid=p.get("OBJECTID")
                parsed=_feature(feature,year,{oid})
                if oid in nifc_orig:
                    raise ValueError("repeated original NIFC ObjectID")
                nifc_orig[oid]=(feature,parsed)
    mtbs_name=f"mtbs-{year}-roi-points.json"
    if mtbs_name not in raws:
        raise ValueError("original MTBS feature response missing")
    mtbs_page=json.loads(raws[mtbs_name])
    if not isinstance(mtbs_page.get("features"),list):
        raise ValueError("original MTBS feature response invalid")
    mtbs_orig={}
    for row in mtbs_page["features"]:
        props=row.get("attributes") or {}
        oid=props.get("objectid")
        parsed=_parse_feature(row,year,{oid})
        if oid in mtbs_orig:
            raise ValueError("repeated original MTBS ObjectID")
        mtbs_orig[oid]=parsed
    if (set(nifc_orig)!=expected_selected["nifc"] or
            set(mtbs_orig)!=expected_selected["mtbs"] or
            len(nifc_orig)!=len(nifc) or len(mtbs_orig)!=len(mtbs)):
        raise ValueError("selected source IDs disagree with original population and feature responses")
    by_nifc={}
    for record in nifc:
        oid=record.get("object_id")
        if oid in by_nifc or oid not in nifc_orig:
            raise ValueError("wrong NIFC selected source ID")
        feature,parsed=nifc_orig[oid]
        if (record.get("feature_sha256")!=parsed[5] or
                record.get("name")!=parsed[3] or
                record.get("source_identity")!=parsed[0] or
                record.get("original_attributes")!=feature["properties"] or
                record.get("geometry")!=feature["geometry"]):
            raise ValueError("NIFC selected source properties or geometry tampered")
        by_nifc[oid]=record
    by_mtbs={}
    for record in mtbs:
        oid=record.get("object_id")
        original=mtbs_orig.get(oid)
        if oid in by_mtbs or original is None or record!=original:
            raise ValueError("MTBS source record tampered")
        by_mtbs[oid]=record
    expected={}
    radius=report.get("candidate_radius_km")
    if type(radius) not in (float,int) or not math.isfinite(radius) or not 1<=radius<=50:
        raise ValueError("invalid candidate radius")
    for m in mtbs:
        for n in nifc:
            if intersects_circle(n["geometry"],latitude=m["latitude"],
                                  longitude=m["longitude"],radius_km=radius):
                expected[(m["object_id"],n["object_id"])]=(m,n)
    provided={}
    for pair in pairs:
        key=(pair.get("mtbs_object_id"),pair.get("nifc_object_id"))
        if key in provided or key not in expected:
            raise ValueError("candidate pair not supported by original provider geometry")
        m,n=expected[key]
        if (pair.get("year")!=year or
                pair.get("mtbs_fire_id")!=m["source_fire_id"] or
                pair.get("mtbs_name")!=m["source_name"] or
                pair.get("mtbs_fire_type")!=m["source_fire_type"] or
                pair.get("nifc_name")!=n["name"] or
                pair.get("within_study_search_radius_only") is not True or
                pair.get("same_event_verified") is not False or
                pair.get("independent_outcome_verified") is not False):
            raise ValueError("candidate falsely claims independent event identity")
        provided[key]=pair
    if set(provided)!=set(expected):
        raise ValueError("missing proximity pair(s) from originally captured source geometry")
    source_digest=_sha(report_bytes)
    result=[]
    for key in sorted(expected):
        m,n=expected[key]
        result.append({
            "candidate_id":f"{year}:mtbs:{m['object_id']}:nifc:{n['object_id']}",
            "year":year,
            "mtbs":{"object_id":m["object_id"],"fire_id":m["source_fire_id"],
                    "name":m["source_name"],"fire_type":m["source_fire_type"],
                    "reported_acres":m["source_reported_acres"],
                    "source_ignition_at":m["source_ignition_at"],
                    "latitude":m["latitude"],"longitude":m["longitude"]},
            "nifc":{"object_id":n["object_id"],"source_identity":n["source_identity"],
                    "name":n["name"],"reported_acres":n["reported_acres"]},
            "preview_rings":_preview(n["geometry"]),
            "preview_is_simplified_not_gis_validated":True,
            "hypothesis_not_ground_truth":True,
        })
    return report,source_digest,result


def render_packet(folder: Path,reviewer_id: str) -> str:
    report,study_sha,rows=load_study(folder)
    _text(reviewer_id,"researcher identity",2)
    if not rows:
        raise ValueError("no proximity candidate pairs to review")
    payload={"schema_version":1,"source_bundle_sha256":study_sha,
             "year":report["year"],"region":report["roi_wgs84_bbox"],
             "reviewer_id":reviewer_id,"cases":rows}
    packed=base64.b64encode(json.dumps(
        payload,ensure_ascii=False,separators=(",",":")).encode()).decode()
    script=SCRIPT.replace("PAYLOAD_BASE64",packed)
    css_sha=base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    js_sha=base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    csp=("default-src 'none'; img-src 'none'; connect-src 'none'; object-src 'none'; "
         "form-action 'none'; base-uri 'none'; script-src 'sha256-"+js_sha+
         "'; style-src 'sha256-"+css_sha+"'")
    esc=lambda x:html.escape(str(x),quote=True)
    return ("""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research pair review · MTBS–NIFC</title>
<meta http-equiv="Content-Security-Policy" content="""+
        '"'+esc(csp)+'">'+
        "<style>"+STYLE+"</style></head><body>"
        "<header><h1>MTBS–NIFC historical proximity research</h1>"
        '<p id="study"></p><p class="quiet">Reviewer: <span id="reviewer"></span> · '
        'Source SHA-256: <code id="digest"></code></p>'
        '<p class="notice">Each pair is only a geographic search candidate. '
        "MTBS may describe prescribed burning and post-fire centroids, not ignitions. "
        "No answer is a verified wildfire identity or independently established nonfire outcome. "
        "This file works offline and never uploads answers. Save by exporting JSON; "
        "closing the page loses unsaved work.</p></header>"
        '<main><nav><button type="button" id="prev">Previous</button>'
        '<strong id="position"></strong><button type="button" id="next">Next</button>'
        '<small id="progress"></small></nav>'
        '<div class="grid"><article><h2>NIFC polygon</h2><p id="nifc"></p>'
        '<p id="identity"></p></article><article><h2>MTBS mapped centroid</h2>'
        '<p id="mtbs"></p><p id="date"></p></article></div>'
        '<h2>Relative geometry preview</h2>'
        '<svg id="review-map" xmlns="http://www.w3.org/2000/svg"></svg>'
        '<small>Illustrative WGS84 preview; coordinates fitted to view, polygon detail '
        'may be reduced. No imagery, GIS topology or event identity is validated.</small>'
        '<label>Manual research disposition<select id="decision">'
        '<option value="unreviewed">Not yet reviewed</option>'
        '<option value="same_event_hypothesis">Possible same event — NOT confirmed</option>'
        '<option value="different_event_hypothesis">Possibly different events — NOT confirmed</option>'
        '<option value="inconclusive">Inconclusive / insufficient evidence</option>'
        '</select></label>'
        '<label>Researcher rationale (at least 15 characters)'
        '<textarea id="reason" placeholder="Explain original sources and limits"></textarea></label>'
        '<label>Independent supporting source URL (HTTPS; mandatory for either hypothesis)'
        '<input id="evidence" type="url" autocomplete="off" placeholder="https://..."></label></main>'
        '<footer><button type="button" id="export">Validate and download research review JSON</button>'
        '<p id="errors" role="alert"></p><p id="status" role="status"></p>'
        '<p class="notice">Classification is a hypothesis; not an adjudicated fire label, '
        'not independent observation, not a detector score.</p></footer>'
        '<script>'+script+"</script></body></html>\n")


def _url(value: object) -> bool:
    if not isinstance(value,str) or not 0<len(value)<=2048:
        return False
    try:
        result=urlsplit(value)
        return result.scheme=="https" and bool(result.hostname) and not result.username
    except ValueError:
        return False


def validate_votes(folder: Path,vote_file: Path) -> dict:
    report,digest,cases=load_study(folder)
    raw=_bounded_file(vote_file,MAX_VOTES_BYTES)
    data=json.loads(raw)
    if (data.get("schema_version")!=1 or
            data.get("source_bundle_sha256")!=digest or
            data.get("classifications_are_unverified_hypotheses") is not True):
        raise ValueError("review does not refer to exact source archive or scientific restrictions")
    reviewer=_text(data.get("reviewer_id"),"reviewer identity",2)
    from .label_review import _utc
    _utc(data.get("reviewed_at"))
    votes=data.get("votes")
    if not isinstance(votes,list) or len(votes)!=len(cases):
        raise ValueError("every proximity candidate needs an explicit decision")
    by_id={c["candidate_id"] for c in cases}
    seen=set()
    counts={k:0 for k in DECISIONS}
    for item in votes:
        if not isinstance(item,dict) or item.get("candidate_id") not in by_id or item["candidate_id"] in seen:
            raise ValueError("duplicate, missing or unrelated reviewed pair")
        seen.add(item["candidate_id"])
        choice=item.get("decision")
        if choice not in DECISIONS:
            raise ValueError("review disposition must be explicit and nonbinary")
        reason=_text(item.get("reason"),"review rationale",15)
        url=item.get("evidence_url")
        if choice!="inconclusive":
            if not _url(url):
                raise ValueError("source URL required for a speculative event hypothesis")
        elif url is not None and not _url(url):
            raise ValueError("optional research URL must be HTTPS")
        counts[choice]+=1
    if seen!=by_id:
        raise ValueError("review missing pair identities")
    return {
        "schema_version":1,"source_bundle_sha256":digest,
        "review_sha256":_sha(raw),"reviewer_id":reviewer,
        "candidates_reviewed":len(cases),"dispositions":counts,
        "same_event_verified":0,"negative_labels_created":0,
        "scientific_status":"manual_hypotheses_not_independent_outcome_validation",
        "source_year":report["year"],
    }


def main() -> None:
    parser=argparse.ArgumentParser(description="Offline MTBS–NIFC proximity pair research")
    sub=parser.add_subparsers(dest="action",required=True)
    make=sub.add_parser("packet")
    make.add_argument("--study-dir",required=True,type=Path)
    make.add_argument("--reviewer-id",required=True)
    make.add_argument("--html",required=True,type=Path)
    check=sub.add_parser("validate")
    check.add_argument("--study-dir",required=True,type=Path)
    check.add_argument("--votes",required=True,type=Path)
    check.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    output=args.html if args.action=="packet" else args.output
    source=args.study_dir
    if (output.exists() or output.resolve().is_relative_to(source.resolve())
            or output.resolve()==source.resolve()):
        parser.error("new research output must be outside original source archive")
    if args.action=="packet":
        contents=render_packet(source,args.reviewer_id)
    else:
        result=validate_votes(source,args.votes)
        if output.resolve()==args.votes.resolve():
            parser.error("cannot overwrite reviewer input")
        contents=json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+"\n"
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as stream:
        stream.write(contents)
    print(json.dumps({"output":str(output),"status":"unverified_manual_pair_review_only",
                      "binary_labels_created":0},sort_keys=True))


if __name__=="__main__":
    main()
