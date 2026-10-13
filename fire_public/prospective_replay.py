"""Read-only offline decision-time replay of prospectively captured agency receipts.

The source-specific record is a research identity anchor, not independent proof
of one physical wildfire, and never creates wildfire absence or extinction labels.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

from .history import _timestamp
from .receipt_history import SOURCES

MAX_CASES = 250
MAX_SCANS = 400
MAX_REPORT_BYTES = 3 * 1024 * 1024
RESEARCH_STATUS = "source_bound_prospective_agency_timeline_not_fire_outcome"
UTC = "2026-10-13T00:00:00Z"


def open_archive(path: Path) -> sqlite3.Connection:
    """No write, migration, implicit DB creation, or external database location."""
    root = Path(__file__).resolve().parents[1]
    if (path.is_symlink() or not path.is_file() or
            path.resolve().is_relative_to(root)):
        raise ValueError("existing local archive must be outside the public repository")
    connection = sqlite3.connect(
        f"file:{quote(str(path.resolve()))}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        expected = {"receipt_scans", "receipt_sources", "receipt_presence",
                    "observations", "fire_event_sources"}
        available = {r[0] for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
        if not expected.issubset(available):
            raise ValueError("this database has no imported prospective agency receipts")
    except Exception:
        connection.close()
        raise
    return connection


def _records(db: sqlite3.Connection, provider: str, official_id: str,
             captured_at: str) -> tuple[dict, str]:
    rows = db.execute("""
        SELECT id, payload_json, observed_at, captured_at, rights_url
        FROM observations WHERE subject_kind = 'agency_incident'
          AND record_type = 'incident_status'
          AND provider = ? AND source_id = ? AND captured_at = ?
        ORDER BY id
    """, (provider, official_id, captured_at)).fetchall()
    if len(rows) != 1:
        raise ValueError("listed original agency identity has missing/ambiguous captured evidence")
    obs = rows[0]
    data = json.loads(obs["payload_json"])
    if (not isinstance(data, dict) or data.get("provider") != provider or
            data.get("official_id") != official_id or
            data.get("kind") != "agency_incident"):
        raise ValueError("corrupt incident data inside archive")
    if (_timestamp(obs["observed_at"]) > _timestamp(captured_at) or
            not obs["rights_url"]):
        raise ValueError("invalid captured source time or rights")
    return data, obs["id"]


def replay(db: sqlite3.Connection, *, at: str, provider: str | None = None,
           official_id: str | None = None) -> dict:
    """Build complete, bounded provenance for all included source identities.

    Caller may rewind to any date, including before the first receipt; only
    evidence actually captured by then is used. Later-discovered identity
    names must not appear in the earlier report.
    """
    cutoff = _timestamp(at)
    if provider is not None and provider not in SOURCES:
        raise ValueError("unsupported agency source; this adapter is for NIFC/CWFIS receipts")
    if official_id is not None and (provider is None or
            not isinstance(official_id, str) or not official_id.strip()):
        raise ValueError("official source ID requires its exact agency provider")
    scan_rows = db.execute("""
        SELECT s.scan_at, s.captured_at, s.run_id, s.snapshot_key,
               s.receipt_sha256, r.provider, r.status
        FROM receipt_scans s JOIN receipt_sources r ON s.scan_at = r.scan_at
        WHERE s.scan_at <= ? AND s.captured_at <= ?
          AND (? IS NULL OR r.provider = ?)
        ORDER BY s.captured_at, s.scan_at, r.provider
    """, (cutoff, cutoff, provider, provider)).fetchall()
    unique_scan_ids = {r["scan_at"] for r in scan_rows}
    if len(unique_scan_ids) > MAX_SCANS:
        raise ValueError("research window exceeds 400 original scans; use --at to bound it")
    if len(scan_rows) != len(unique_scan_ids)*(1 if provider else len(SOURCES)):
        raise ValueError("source states incomplete or duplicate in original agency scan")
    allowed_status = {"complete", "failed", "deferred"}
    scans = []
    scan_index = {}
    for r in scan_rows:
        if (r["status"] not in allowed_status or
                not re.fullmatch(r"[a-f0-9]{64}", r["receipt_sha256"]) or
                not re.fullmatch(r"snapshot:[a-f0-9]{64}", r["snapshot_key"]) or
                not re.fullmatch(r"[1-9]\d*", r["run_id"]) or
                _timestamp(r["scan_at"]) > _timestamp(r["captured_at"])):
            raise ValueError("invalid historical scan provenance")
        row = {k: r[k] for k in ("scan_at", "captured_at", "run_id", "snapshot_key",
                                "receipt_sha256", "provider", "status")}
        scans.append(row)
        scan_index[(row["scan_at"], row["provider"])] = row

    selection = db.execute("""
        SELECT DISTINCT p.provider, p.official_id
        FROM receipt_presence p JOIN receipt_scans s ON s.scan_at = p.scan_at
        WHERE s.scan_at <= ? AND s.captured_at <= ?
          AND (? IS NULL OR p.provider = ?)
          AND (? IS NULL OR p.official_id = ?)
        ORDER BY p.provider, p.official_id LIMIT ?
    """, (cutoff, cutoff, provider, provider, official_id, official_id, MAX_CASES+1)).fetchall()
    if len(selection) > MAX_CASES:
        raise ValueError("more than 250 known source identities; select --provider and --official-id")
    by_provider = {name: [r for r in scans if r["provider"] == name]
                   for name in (SOURCES if provider is None else (provider,))}
    cases = []
    for id_row in selection:
        p, oid = id_row["provider"], id_row["official_id"]
        source_scans = by_provider[p]
        trace = []
        last_listed_at = None
        latest_name = None
        for s in source_scans:
            presence = db.execute("""
                SELECT agency_status FROM receipt_presence
                WHERE scan_at = ? AND provider = ? AND official_id = ?
            """, (s["scan_at"], p, oid)).fetchone()
            if s["status"] != "complete":
                if presence:
                    raise ValueError("failed source cannot independently list an incident")
                availability = "source_unavailable"
                agency_status = None
                observation_id = None
                source_modified_at = None
                source_name = None
            elif presence is None:
                availability = "not_listed_in_complete_scan"
                agency_status = None
                observation_id = None
                source_modified_at = None
                source_name = None
            else:
                availability = "listed"
                data, observation_id = _records(db,p,oid,s["captured_at"])
                if data.get("agency_status") != presence["agency_status"]:
                    raise ValueError("archived agency status differs from source-layer receipt")
                agency_status = presence["agency_status"]
                source_modified_at = data.get("modified_at")
                if source_modified_at and _timestamp(source_modified_at) > _timestamp(s["captured_at"]):
                    raise ValueError("future agency modification inside archival record")
                source_name = data.get("name")
                latest_name = source_name or latest_name
                last_listed_at = s["captured_at"]
            trace.append({
                "scan_at":s["scan_at"],"captured_at":s["captured_at"],
                "source_status":s["status"],"availability":availability,
                "agency_status":agency_status,"source_modified_at":source_modified_at,
                "source_name":source_name,"observation_sha256":observation_id,
                "receipt_sha256":s["receipt_sha256"],"run_id":s["run_id"],
                "last_listed_at":last_listed_at,
                "extinguishment_label":None,"event_identity_independently_verified":False
            })
        first = next((t for t in trace if t["availability"]=="listed"),None)
        if first is None:
            raise ValueError("source identity existed without a successfully listed scan")
        current = trace[-1]
        changes = sum(t["availability"]!=trace[i-1]["availability"] or
                      (t["availability"]=="listed" and
                       t["agency_status"]!=trace[i-1]["agency_status"])
                      for i,t in enumerate(trace) if i>0)
        cases.append({
            "provider":p, "official_id":oid,
            "source_identity":json.dumps([p,oid],separators=(",",":")),
            "latest_known_name":latest_name,
            "first_available_at":first["captured_at"],
            "last_listed_at":last_listed_at,
            "latest_availability":current["availability"],
            "latest_agency_status":current["agency_status"],
            "observed_state_changes":changes,
            "timeline":trace,
            "physical_fire_identity_verified":False,
            "verified_extinguishment_at":None,
            "verified_nonfire":False,
        })
    result = {
        "schema_version":1,"research_status":RESEARCH_STATUS,
        "maturity":"experimental_prospective_receipt_replay",
        "as_of":cutoff, "provider_filter":provider,
        "official_id_filter":official_id,
        "agency_scan_count":len(unique_scan_ids),
        "source_scan_rows":len(scans),
        "known_source_identities":len(cases),
        "scans":scans,"cases":cases,
        "verified_cross_provider_event_links":0,
        "verified_nonfire_labels":0,"verified_extinguishment_labels":0,
        "forecast_skill_measured":False,
        "limitations":[
            "Source IDs are provider-specific; no NIFC/CWFIS or FIRMS identity merger is inferred.",
            "Only successfully captured prospective receipts can be replayed at the specified decision time.",
            "Provider modified_at may be older than receipt; archive availability begins at captured_at.",
            "An absent entry in a complete current provider layer is not a declaration of extinguishment.",
            "Failed or deferred source runs mean unknown visibility; earlier source observations are not new confirmations.",
            "Agency source states do not authenticate independent physical wildfire identities or guarantee geographic coverage.",
            "This local subset is not a full global incident census or a fire-risk model.",
        ]
    }
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",",":"),
                     allow_nan=False).encode()
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("source replay exceeds 3 MiB; select one provider or source ID")
    return result


CSS = """
:root{font-family:system-ui,sans-serif;color-scheme:light;background:#f4f7f8;color:#1c3540}
*{box-sizing:border-box}body{margin:0;line-height:1.5}header{background:#203f4a;color:white;padding:17px 22px}
header h1{font-size:1.55rem;margin:0}header p{margin:7px 0;font-size:.9rem;max-width:90ch}
main{display:grid;grid-template-columns:minmax(250px,360px) minmax(0,1fr)}
aside{padding:15px;background:white;border-right:1px solid #c5d6d8}
article{padding:18px;min-width:0}h2{font-size:1.35rem}h3{font-size:1.1rem}
select,input,button{font:inherit;padding:8px;border-radius:5px}
input,select{border:1px solid #7c9aa3;width:100%}button{background:#215367;color:white;border:0;cursor:pointer}
button[aria-pressed=true]{background:#daf1ec;color:#133642;border:2px solid #116574}
button:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #b86e11;outline-offset:2px}
#event-list{list-style:none;padding:0;max-height:60vh;overflow-y:auto}
#event-list button{width:100%;text-align:left;margin:4px 0;overflow-wrap:anywhere}
#event-list small{display:block}.warning{color:#854507;font-weight:650}
header .warning{color:#ffdd96}.muted{color:#52676d}
table{border-collapse:collapse;width:100%;font-size:.84rem}th,td{border-bottom:1px solid #c8d9db;padding:8px;text-align:left;overflow-wrap:anywhere}
th{background:#e4eff1}tr[data-state="source_unavailable"]{background:#fff1db}
tr[data-state="not_listed_in_complete_scan"]{background:#f2f1e6}
#trace{overflow-x:auto;max-width:100%}section{margin:16px 0}
header,article,aside,p,code{overflow-wrap:anywhere}
@media(max-width:750px){main{grid-template-columns:1fr}aside{border-right:0;border-bottom:1px solid #c5d6d8}
article{padding:12px}header{padding:12px}}
"""


def offline_html(report: dict) -> str:
    if (report.get("research_status") != RESEARCH_STATUS or
        report.get("verified_cross_provider_event_links") != 0 or
        report.get("verified_nonfire_labels") != 0 or
        report.get("verified_extinguishment_labels") != 0 or
        report.get("forecast_skill_measured") is not False):
        raise ValueError("no verified wildfire/nonfire claims can be rendered")
    script_source = Path(__file__).with_name("prospective_replay.js").read_text("utf-8")
    payload = base64.b64encode(json.dumps(report,sort_keys=True,ensure_ascii=False,
       allow_nan=False,separators=(",",":")).encode()).decode()
    script = (script_source +
              "\nAgencyReplay.mount(document,JSON.parse(new TextDecoder('utf-8').decode("
              "Uint8Array.from(atob('" + payload + "'),c=>c.charCodeAt(0)))));\n")
    token = base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
    style_token = base64.b64encode(hashlib.sha256(CSS.encode()).digest()).decode()
    csp = ("default-src 'none'; connect-src 'none'; script-src 'sha256-"+token+
           "'; style-src 'sha256-"+style_token+
           "'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'")
    esc=lambda s:html.escape(s,quote=True)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
      '<meta name="viewport" content="width=device-width,initial-scale=1">'
      '<meta http-equiv="Content-Security-Policy" content="'+esc(csp)+'">'
      '<title>Offline agency incident time machine</title><style>'+CSS+'</style></head>'
      '<body><header><h1>Source receipt time machine</h1>'
      '<p class="warning">Research only: not wildfire confirmation, extinguishment, '
      'fire absence or a forecast. Agency incident identity is source-specific.</p>'
      '<p id="asof-source"></p></header>'
      '<main><aside><label for="moment">Replay known decision time</label>'
      '<select id="moment"></select><label for="find">Search agency source identities</label>'
      '<input id="find" type="search" placeholder="Agency, name or exact source ID">'
      '<p id="count" role="status"></p><ol id="event-list"></ol></aside>'
      '<article><button id="download" type="button">Export selected as-of evidence JSON</button>'
      '<p id="quality" class="warning" role="status"></p><div id="detail"></div></article></main>'
      '<script>'+script+'</script></body></html>\n')


def _write_private(output: Path, report: dict) -> None:
    root=Path(__file__).resolve().parents[1]
    if (output.is_symlink() or output.exists() or
        output.resolve().is_relative_to(root) or
        not output.parent.is_dir() or output.parent.is_symlink()):
        raise ValueError("choose a new output directory outside Git with an existing private parent")
    output.mkdir(mode=0o700)
    try:
        data={
          "index.html":offline_html(report).encode(),
          "evidence.json":(json.dumps(report,ensure_ascii=False,sort_keys=True,
                        indent=2,allow_nan=False)+"\n").encode()
        }
        for name,content in data.items():
            file=output/name
            with file.open("xb") as fp:
                fp.write(content)
            file.chmod(0o600)
    except Exception:
        for file in output.iterdir():
            file.unlink()
        output.rmdir()
        raise


def main() -> None:
    parser=argparse.ArgumentParser(
        description="Offline read-only source-bound agency event time machine")
    parser.add_argument("--db",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--at",help="UTC-aware maximum receipt time; defaults to latest actual capture")
    parser.add_argument("--provider",choices=SOURCES)
    parser.add_argument("--official-id")
    args=parser.parse_args()
    if args.official_id and not args.provider:
        parser.error("--official-id requires --provider")
    conn=open_archive(args.db)
    try:
        if args.at:
            at=args.at
        else:
            row=conn.execute("SELECT MAX(captured_at) FROM receipt_scans").fetchone()
            if not row or not row[0]:
                raise ValueError("no prospective receipt observations in archive")
            at=row[0]
        report=replay(conn,at=at,provider=args.provider,official_id=args.official_id)
    finally:
        conn.close()
    _write_private(args.output_dir,report)
    print(json.dumps({"cases":report["known_source_identities"],
       "scans":report["agency_scan_count"],"as_of":report["as_of"],
       "verified_extinguishment_labels":0,
       "files":["index.html","evidence.json"]},sort_keys=True))


if __name__ == "__main__":
    main()
