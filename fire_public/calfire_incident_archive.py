"""Actual CAL FIRE 2018 *incident archive* compared with real NIFC/MTBS leads.

Original CAL FIRE HTML is retained with exact SHA. Cross references are only
source-name / retrospective-date investigation leads: no verified event IDs,
source independence, fire negatives, spatial corroboration or forecast skill.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlparse
from urllib.request import Request, build_opener

from .official_perimeters import _RejectRedirects
from .mtbs_match_review import load_study
from .mtbs_candidate_triage import _distinctive_tokens

SOURCE="https://www.fire.ca.gov/incidents/2018"
MAX_HTML=6*1024*1024
MAX_RECORDS=1500
MAX_CANDIDATES=1600


def _norm(value: str) -> str:
    text=unicodedata.normalize("NFKC",value).casefold()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in text).split())


def _date(s: str) -> str | None:
    s=s.strip()
    try:
        parsed=datetime.strptime(s,"%m/%d/%Y").date()
    except ValueError:
        return None
    return parsed.isoformat()


class ArchiveRows(HTMLParser):
    """Read only full five-column original CAL FIRE incident archive table rows."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[]
        self._row=None
        self._cell=None
        self._anchor=None
        self._links=[]
        self._table_depth=0
        self._headings=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="table":
            self._table_depth+=1
        if tag=="tr" and self._table_depth:
            self._row=[]
            self._links=[]
        if tag in ("th","td") and self._row is not None:
            self._cell=[]
        if tag=="a" and self._cell is not None:
            self._anchor=attrs.get("href")
    def handle_data(self,data):
        if self._cell is not None:
            self._cell.append(data)
    def handle_endtag(self,tag):
        if tag in ("th","td") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell=None
        if tag=="a":
            if self._anchor is not None and self._row is not None:
                self._links.append(self._anchor)
            self._anchor=None
        if tag=="tr" and self._row is not None:
            if len(self._row)==5:
                self.rows.append((self._row,tuple(self._links)))
            self._row=None
        if tag=="table" and self._table_depth:
            self._table_depth-=1


def _incident_path(link: str) -> str | None:
    parsed=urlparse(link)
    if parsed.scheme or parsed.netloc:
        if (parsed.scheme!="https" or parsed.hostname!="www.fire.ca.gov"
                or parsed.port is not None):
            return None
    path=parsed.path
    if path.startswith("/incidents/2018/") and len(path)>len("/incidents/2018/"):
        return "https://www.fire.ca.gov"+path
    return None


def parse_archive(raw: bytes) -> list[dict]:
    if not 0<len(raw)<=MAX_HTML:
        raise ValueError("CAL FIRE original HTML missing or oversized")
    text=raw.decode("utf-8-sig")
    if "2018 Incidents" not in text and "2018 Fire Season" not in text:
        raise ValueError("CAL FIRE original source is not the pinned 2018 incident archive")
    parser=ArchiveRows()
    parser.feed(text)
    headings=[cells for cells,_ in parser.rows
              if cells and cells[0].strip().casefold()=="incident"]
    if not any([h.casefold() for h in heading][:4]==[
            "incident","counties","started","acres"] for heading in headings):
        raise ValueError("2018 CAL FIRE incident table headers changed")
    incidents=[]
    for values,links in parser.rows:
        name, counties, started, acres, containment=values
        if name.casefold()=="incident":
            continue
        if not name or len(name)>240:
            raise ValueError("CAL FIRE incident source name missing or malformed")
        urls=sorted(set(url for link in links if (url:=_incident_path(link))))
        if len(urls)!=1:
            raise ValueError("CAL FIRE original incident archive row lacks a unique official event page")
        try:
            n_acres=int(acres.replace(",",""))
        except ValueError as exc:
            raise ValueError("CAL FIRE source acres not numeric") from exc
        if not 0<=n_acres<=20_000_000:
            raise ValueError("CAL FIRE source acreage outside conservative range")
        date=_date(started)
        incidents.append({
            "name":name,"counties":counties,
            "source_started_at":date,
            "source_started_raw":started,
            "started_year_is_requested_2018":bool(date and date[:4]=="2018"),
            "reported_acres":n_acres,
            "containment_source_text":containment,
            "original_event_url":urls[0],
            "retrospective_archive_record":True,
            "independently_authenticated_event_identity":False,
        })
    if not 10<=len(incidents)<=MAX_RECORDS:
        raise ValueError("CAL FIRE archive parsed no plausible 2018 incident rows")
    return incidents


def fetch_archive() -> bytes:
    request=Request(SOURCE,headers={
        "User-Agent":"WildfireSignals-CALFIRE-Historical-Research/1",
        "Accept":"text/html"})
    with build_opener(_RejectRedirects()).open(request,timeout=40) as response:
        body=response.read(MAX_HTML+1)
    if not 0<len(body)<=MAX_HTML:
        raise ValueError("CAL FIRE official archive exceeds 6MiB hard budget")
    return body


def compare(study_dir: Path,original_html: bytes,*,captured_at: str) -> dict:
    study,study_digest,cases=load_study(study_dir)
    if study["year"]!=2018:
        raise ValueError("pinned CAL FIRE archive is 2018 only")
    parsed=datetime.fromisoformat(captured_at.replace("Z","+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("source capture time must be UTC offset aware")
    incidents=parse_archive(original_html)
    all_hits=[]
    counters={"exact_normalized_source_name":0,"shared_distinctive_name_tokens":0,
              "no_name_based_external_archive_leads":0}
    for case in cases:
        found=[]
        names=(( "mtbs",case["mtbs"]["name"]),
               ("nifc",case["nifc"]["name"]))
        for ix,incident in enumerate(incidents):
            matches=[]
            for provider,raw_name in names:
                if not isinstance(raw_name,str):
                    continue
                normalized=_norm(raw_name)
                if not normalized:
                    continue
                external=_norm(incident["name"])
                if normalized==external:
                    matches.append({"source_name":provider,
                                    "signal":"exact_normalized_name_only"})
                else:
                    left=_distinctive_tokens(raw_name)
                    right=_distinctive_tokens(incident["name"])
                    shared=sorted(tok for tok in left&right if len(tok)>=4)
                    if shared:
                        matches.append({"source_name":provider,
                                        "signal":"distinctive_token_shared_not_identity",
                                        "tokens":shared[:12]})
            if not matches:
                continue
            mtbs_date=case["mtbs"]["source_ignition_at"]
            comparisons={
                "mtbs_date_available":mtbs_date is not None,
                "calfire_date_available":incident["source_started_at"] is not None,
                "same_calendar_start_day_if_both_present": (
                    mtbs_date[:10]==incident["source_started_at"] if mtbs_date and
                    incident["source_started_at"] else None),
                "original_nifc_ignition_date_available":False,
            }
            found.append({
                "archive_row_ordinal":ix+1,
                "calfire_name":incident["name"],
                "calfire_event_url":incident["original_event_url"],
                "calfire_started_at":incident["source_started_at"],
                "calfire_counties":incident["counties"],
                "calfire_reported_acres":incident["reported_acres"],
                "name_signals":matches,
                "retrospective_date_comparison":comparisons,
                "same_fire_event_verified":False,
                "third_party_independence_verified":False,
            })
        found.sort(key=lambda x:(x["calfire_name"],x["calfire_event_url"]))
        if not found:
            kind="no_name_based_external_archive_leads"
        elif any(any(s["signal"]=="exact_normalized_name_only" for s in row["name_signals"])
                 for row in found):
            kind="exact_normalized_source_name"
        else:
            kind="shared_distinctive_name_tokens"
        counters[kind]+=1
        all_hits.append({
            "candidate_id":case["candidate_id"],
            "mtbs_fire_id":case["mtbs"]["fire_id"],
            "mtbs_name":case["mtbs"]["name"],
            "nifc_source_identity":case["nifc"]["source_identity"],
            "nifc_name":case["nifc"]["name"],
            "evidence_lead_status":kind,
            "calfire_name_only_leads":found,
            "candidate_fire_event_identity_verified":False,
            "missing_calfire_name_lead_is_not_nonfire":True,
        })
    return {
        "schema_version":1,
        "source":"CAL_FIRE_official_2018_incident_archive",
        "source_url":SOURCE,
        "source_capture_at":parsed.astimezone(timezone.utc).isoformat(),
        "source_original_html_sha256":hashlib.sha256(original_html).hexdigest(),
        "source_original_html_bytes":len(original_html),
        "nifc_mtbs_source_study_sha256":study_digest,
        "calfire_archive_records_parsed":len(incidents),
        "archive_records_with_non2018_or_unknown_dates":sum(
            not x["started_year_is_requested_2018"] for x in incidents),
        "archive_not_necessarily_all_fires":True,
        "source_upstream_independence_from_nifc_or_mtbs_unverified":True,
        "research_leads_by_case":counters,
        "case_count":len(all_hits),
        "cases":all_hits,
        "confirmed_event_identity_count":0,
        "verified_nonfire_labels":0,
        "calibrated_model_accuracy_measured":False,
        "interpretation":"Names and retrospectively reported dates only. CAL FIRE and NIFC may share underlying agency event records. No match/no match is NOT independently established event identity, complete incident coverage, wildfire absence, or forecast skill.",
    }


def save(path: Path,archive_html: bytes,report: dict) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError("new original source archive destination required")
    if (hashlib.sha256(archive_html).hexdigest()!=report["source_original_html_sha256"] or
            len(archive_html)!=report["source_original_html_bytes"]):
        raise ValueError("raw official archive bytes inconsistent with report")
    path.mkdir(parents=True,mode=0o700)
    try:
        with (path/"original-calfire-2018.html").open("xb") as out:
            out.write(archive_html)
        with (path/"original-calfire-cross-reference.json").open("x",encoding="utf-8") as out:
            json.dump(report,out,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)
            out.write("\n")
    except BaseException:
        for f in path.iterdir():
            if f.is_file(): f.unlink()
        path.rmdir()
        raise


def replay(study_dir: Path,archive: Path) -> dict:
    raw=(archive/"original-calfire-2018.html").read_bytes()
    existing=json.loads((archive/"original-calfire-cross-reference.json").read_text())
    generated=compare(study_dir,raw,captured_at=existing["source_capture_at"])
    if generated!=existing:
        raise ValueError("CAL FIRE archive report changed or original source bytes are corrupted")
    return generated


def main() -> None:
    p=argparse.ArgumentParser(description="Actual CAL FIRE 2018 archive leads vs NIFC/MTBS; research only")
    p.add_argument("--study-dir",required=True,type=Path)
    p.add_argument("--output-dir",required=True,type=Path)
    args=p.parse_args()
    source=fetch_archive()
    report=compare(args.study_dir,source,captured_at=datetime.now(timezone.utc).isoformat())
    save(args.output_dir,source,report)
    replay(args.study_dir,args.output_dir)
    print(json.dumps({"source_archive_rows":report["calfire_archive_records_parsed"],
                      "case_count":report["case_count"],
                      "name_leads":report["research_leads_by_case"],
                      "confirmed_event_identities":0,"verified_nonfire_labels":0},sort_keys=True))


if __name__=="__main__":
    main()
