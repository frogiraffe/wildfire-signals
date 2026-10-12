"""Offline historical incident intelligence workbench.

Only provider evidence captured by the requested decision time is shown.
This module never promotes FIRMS candidates to verified fires and never infers
extinguishment from disappearance in an active agency layer.
"""
from __future__ import annotations

import argparse
import html
import json
import math
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from .history import _timestamp
from .region_diagnostics import distance_km
from .historical_context import (archived_candidates, archived_weather_context,
                                 archived_release_pixel_evidence)

MAX_EVENTS = 500
MAX_EVIDENCE_PER_EVENT = 100
PROVIDERS = ("cwfis", "nifc_wfigs")


def _read_db(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"history archive does not exist: {path}")
    # URI read-only mode: reporting must never initialize, migrate or mutate an archive.
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _table_present(db: sqlite3.Connection, name: str) -> bool:
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                      (name,)).fetchone() is not None


def _coordinates(payload: dict) -> tuple[float, float] | None:
    try:
        lat, lon = float(payload["latitude"]), float(payload["longitude"])
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    except (TypeError, ValueError, KeyError):
        pass
    return None


def _source_scans(db: sqlite3.Connection, cutoff: str) -> tuple[dict, list]:
    """Latest source states plus receipt gaps; never interpolate unavailable scans."""
    latest = {name: {"status": "no_receipt_yet", "scan_at": None,
                     "captured_at": None, "listed_ids": set()} for name in PROVIDERS}
    gaps = []
    if not all(_table_present(db, n) for n in
               ("receipt_scans", "receipt_sources", "receipt_presence")):
        return latest, gaps
    scans = db.execute("""
        SELECT s.scan_at, s.captured_at, r.provider, r.status
        FROM receipt_scans s JOIN receipt_sources r ON r.scan_at=s.scan_at
        WHERE s.scan_at<=? AND s.captured_at<=?
        ORDER BY s.captured_at ASC, s.scan_at ASC
    """, (cutoff, cutoff)).fetchall()
    recent_scan = None
    for row in scans:
        # Count receipt gaps once (two providers can share one timestamp).
        if row["scan_at"] != recent_scan:
            recent_scan = row["scan_at"]
            gaps.append({"scan_at": row["scan_at"], "captured_at": row["captured_at"]})
        provider = row["provider"]
        if provider in latest:
            latest[provider] = {"status": row["status"], "scan_at": row["scan_at"],
                                "captured_at": row["captured_at"], "listed_ids": set()}
    for provider, current in latest.items():
        if current["status"] == "complete":
            rows = db.execute("""
                SELECT official_id FROM receipt_presence
                WHERE scan_at=? AND provider=?
            """, (current["scan_at"], provider))
            current["listed_ids"] = {row["official_id"] for row in rows}
    actual_gaps = []
    for before, after in zip(gaps, gaps[1:]):
        delta = (datetime.fromisoformat(after["scan_at"]) -
                 datetime.fromisoformat(before["scan_at"])).total_seconds() / 3600
        if delta > 9:
            actual_gaps.append({"from": before["scan_at"], "to": after["scan_at"],
                                "hours": round(delta, 3)})
    return latest, actual_gaps


def _availability(source: dict, source_id: str) -> str:
    if source["status"] in ("failed", "deferred"):
        return "source_unavailable"
    if source["status"] == "no_receipt_yet":
        return "no_receipt_yet"
    if source["status"] != "complete":
        return "source_unknown"
    return ("listed_in_latest_complete_scan" if source_id in source["listed_ids"]
            else "not_listed_in_latest_complete_scan")


def build_workbench(path: str | Path, *, at: str, latitude: float | None = None,
                    longitude: float | None = None, radius_km: float | None = None,
                    limit: int = 200, weather_db: str | Path | None = None,
                    satellite_hours: int = 72,
                    pixel_db: str | Path | None = None) -> dict:
    """Read real archives with explicit decision-time and optional global circle.

    All coordinate inputs are required together. Lack of an official observation
    or an unavailable provider must not be interpreted as a fire-negative label.
    """
    cutoff = _timestamp(at)
    region_given = any(x is not None for x in (latitude, longitude, radius_km))
    if region_given and not all(x is not None for x in (latitude, longitude, radius_km)):
        raise ValueError("latitude, longitude and radius_km are required together")
    if region_given:
        values = (latitude, longitude, radius_km)
        if (not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)
            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180
            or not 0 < radius_km <= 20000):
            raise ValueError("Invalid worldwide search circle")
    if type(limit) is not int or not 1 <= limit <= MAX_EVENTS:
        raise ValueError(f"limit must be 1..{MAX_EVENTS}")

    db = _read_db(Path(path))
    try:
        if not _table_present(db, "fire_event_sources") or not _table_present(db, "observations"):
            raise ValueError("Not a compatible HistoryStore database")
        sources, gaps = _source_scans(db, cutoff)
        # Iterate with a stable order; bound the *rendered* result rather than silently
        # claiming we sampled all incidents when the report is truncated.
        identities = db.execute("""
            SELECT provider, source_id, event_id, first_captured_at
            FROM fire_event_sources WHERE first_captured_at <= ?
            ORDER BY first_captured_at DESC, provider, source_id
        """, (cutoff,)).fetchall()
        entries = []
        without_coordinates = 0
        outside_region = 0
        for identity in identities:
            rows = db.execute("""
                SELECT record_type, observed_at, captured_at, source_url,
                       rights_url, payload_json, id
                FROM observations
                WHERE subject_kind='agency_incident' AND provider=? AND source_id=?
                  AND observed_at<=? AND captured_at<=?
                ORDER BY captured_at, observed_at, id
            """, (identity["provider"], identity["source_id"], cutoff, cutoff)).fetchall()
            if not rows:
                continue
            current = None
            for row in reversed(rows):
                if row["record_type"] == "incident_status":
                    current = json.loads(row["payload_json"])
                    break
            # Retrospective-only perimeters may have no incident-status observations.
            coords = _coordinates(current or {})
            if coords is None:
                for row in reversed(rows):
                    coords = _coordinates(json.loads(row["payload_json"]))
                    if coords is not None:
                        break
            if region_given:
                if coords is None:
                    without_coordinates += 1
                    continue
                if distance_km(latitude, longitude, *coords) > radius_km:
                    outside_region += 1
                    continue

            provider = identity["provider"]
            availability = _availability(sources.get(provider, {"status":"no_receipt_yet"}), identity["source_id"])
            recent = rows[-MAX_EVIDENCE_PER_EVENT:]
            timeline = []
            previous_status = None
            for row in recent:
                payload = json.loads(row["payload_json"])
                status = (payload.get("agency_status") or payload.get("stage_of_control_status")
                          or payload.get("status")) if row["record_type"] == "incident_status" else None
                timeline.append({"record_type": row["record_type"], "observed_at": row["observed_at"],
                                 "captured_at": row["captured_at"], "source_url": row["source_url"],
                                 "rights_url": row["rights_url"], "source_hash": row["id"],
                                 "reported_status": status})
                if status is not None:
                    previous_status = status
            entries.append({
                "event_id": identity["event_id"], "provider": provider,
                "official_id": identity["source_id"],
                "name": (current or {}).get("name") or identity["source_id"],
                "location": {"latitude": coords[0], "longitude": coords[1]} if coords else None,
                "reported_status": previous_status,
                "source_layer_availability": availability,
                "first_captured_at": identity["first_captured_at"],
                "latest_evidence_captured_at": rows[-1]["captured_at"],
                "evidence_count": len(rows),
                "evidence_truncated": len(rows) > MAX_EVIDENCE_PER_EVENT,
                "timeline": timeline,
            })
        rendered = entries[:limit]
        sat_region = ({"latitude":latitude,"longitude":longitude,"radius_km":radius_km}
                      if region_given else None)
        satellite = (archived_release_pixel_evidence(pixel_db,at=cutoff,
                     hours=satellite_hours,region=sat_region) if pixel_db is not None
                     else archived_candidates(db,at=cutoff,hours=satellite_hours,
                                              region=sat_region))
        weather = archived_weather_context(weather_db, rendered, at=cutoff) if weather_db is not None else None
        if weather is not None:
            by_event = {r["event_id"]:r["forecast"] for r in weather["event_contexts"]}
            for item in rendered:
                item["weather_context"] = by_event[item["event_id"]]
        summary = {
            "schema_version": 2, "decision_at": cutoff,
            "satellite_evidence": satellite,
            "weather_evidence": weather,
            "scope": {"type": "circle", "latitude": latitude, "longitude": longitude,
                      "radius_km": radius_km} if region_given else {"type": "archive"},
            "agency_identities_in_archive": len(identities),
            "matched_identities": len(entries),
            "shown": len(rendered), "truncated": len(entries) > len(rendered),
            "missing_coordinates_in_region_search": without_coordinates,
            "outside_region": outside_region,
            "source_states": {p: {k:v for k,v in data.items() if k != "listed_ids"}
                              for p,data in sources.items()},
            "receipt_gaps_over_9_hours": gaps,
            "availability_counts": dict(sorted(Counter(
                e["source_layer_availability"] for e in entries).items())),
            "incidents": rendered,
            "notices": [
                "This is offline agency evidence captured by the selected decision time, not a live fire map.",
                "Satellite thermal candidates are not independent wildfire confirmations.",
                "Missing from a complete active agency layer does not mean extinguished.",
                "Source outages, unobserved intervals and missing coordinates limit conclusions.",
                "Historical records obtained later cannot be used as if known at their source observation time.",
            ],
            "validated_prediction": False,
            "extinguishment_labels_created": 0,
        }
        return summary
    finally:
        db.close()


def render_html(report: dict) -> str:
    """Self-contained, script-free, escaped HTML for offline inspection."""
    esc = lambda x: html.escape(str(x), quote=True)
    lines = ["""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wildfire Signals | Historical Evidence Workbench</title>
<style>
:root{font-family:system-ui,sans-serif;background:#0f1a23;color:#f2f6f8}
body{max-width:1150px;margin:0 auto;padding:24px;line-height:1.5}
h1{font-size:1.8rem}h2{font-size:1.2rem}h3{font-size:1rem}
header,.panel,details{background:#192b36;border:1px solid #335160;border-radius:12px;padding:16px;margin:12px 0}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}
.summary div{padding:13px;background:#253d49;border-radius:9px}
.summary strong{font-size:1.6rem;display:block}small,.muted{color:#c0d3d8}
table{border-collapse:collapse;width:100%;font-size:.85rem;word-break:break-word}
th,td{text-align:left;border-bottom:1px solid #345160;padding:7px;vertical-align:top}
th{color:#a9cdd1}summary{cursor:pointer;font-weight:650}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;background:#345260;font-size:.75rem}
.critical{color:#f6c58f}a{color:#9bdad7}
@media(max-width:650px){body{padding:10px}table{font-size:.72rem}th,td{padding:4px}}
</style></head><body>"""]
    lines.append("<header><h1>Historical Evidence Workbench</h1>")
    lines.append(f"<p>Decision time (UTC): <strong>{esc(report['decision_at'])}</strong></p>")
    lines.append("<p class='critical'>Offline source history, not current fire status or a prediction.</p></header>")
    lines.append("<section class='summary' aria-label='Evidence summary'>")
    for label,value in (("Archived identities",report["agency_identities_in_archive"]),
                        ("Matched",report["matched_identities"]),("Displayed",report["shown"]),
                        ("Receipt gaps >9h",len(report["receipt_gaps_over_9_hours"]))):
        lines.append(f"<div><strong>{esc(value)}</strong><span>{esc(label)}</span></div>")
    lines.append("</section><section class='panel'><h2>Scope and source availability</h2>")
    lines.append(f"<p>{esc(json.dumps(report['scope'],ensure_ascii=False))}</p><ul>")
    for provider,state in report["source_states"].items():
        lines.append(f"<li><b>{esc(provider)}</b>: {esc(state['status'])}, scan {esc(state['scan_at'])}</li>")
    lines.append("</ul>")
    for notice in report["notices"]:
        lines.append(f"<p class='muted'>{esc(notice)}</p>")
    if report["truncated"]:
        lines.append("<p class='critical'>Results truncated by the requested display limit.</p>")
    lines.append("</section>")
    satellite = report.get("satellite_evidence")
    if satellite:
        lines.append("<section class='panel'><h2>Archived satellite candidates (not confirmed fires)</h2>")
        lines.append(f"<p>Window: {esc(satellite['window_hours'])} hours. "
                     f"Archive records ({esc(satellite.get('observation_unit','candidate_cell_hours'))}): "
                     f"{esc(satellite['available_archive_records'])}; "
                     f"observed cells: {esc(satellite['distinct_observed_cells'])}; "
                     f"repeated cells: {esc(satellite['cells_observed_in_multiple_hours'])}.</p>")
        lines.append(f"<p>Latest observation: {esc(satellite['latest_observed_at'])}; "
                     f"truncated evidence query: {esc(satellite['row_limit_reached'])}</p>")
        if "candidate_cell_hours" in satellite:
            lines.append(f"<p>Grouped 0.05° candidate cell-hours: "
                         f"{esc(satellite['candidate_cell_hours'])}; "
                         f"captured scan receipts: {esc(satellite['scan_count'])}.</p>")
            for source,state in satellite.get("latest_source_state",{}).items():
                lines.append(f"<p>{esc(source)} source: {esc(state['status'])} "
                             f"(scan {esc(state['scan_at'])})</p>")
        lines.append(f"<p class='critical'>{esc(satellite['note'])}</p></section>")
    weather = report.get("weather_evidence")
    if weather:
        lines.append("<section class='panel'><h2>Captured NWS forecast evidence</h2>")
        lines.append(f"<p>{esc(weather['scope'])}. Captured eligible forecast receipts: "
                     f"{esc(weather['eligible_archive_forecasts'])}.</p>")
        if weather["archive_row_limit_reached"]:
            lines.append("<p class='critical'>Weather archive query limit reached; results may be incomplete.</p>")
        lines.append("</section>")
    lines.append("<section class='panel'><h2>Event evidence and capture timeline</h2>")
    if not report["incidents"]:
        lines.append("<p>No matching incident evidence was available by this decision time.</p>")
    for item in report["incidents"]:
        label = f"{item['provider']} · {item['name']}"
        lines.append(f"<details><summary>{esc(label)} <span class='badge'>{esc(item['source_layer_availability'])}</span></summary>")
        lines.append(f"<p>Event ID: {esc(item['event_id'])} · Official ID: {esc(item['official_id'])}</p>")
        lines.append(f"<p>Reported source status: {esc(item['reported_status'])}; "
                     f"evidence records: {esc(item['evidence_count'])}</p>")
        if item["location"]:
            lines.append(f"<p>Location: {esc(item['location']['latitude'])}, "
                         f"{esc(item['location']['longitude'])}</p>")
        if item.get("weather_context") is not None:
            forecast = item["weather_context"]
            lines.append(f"<p>Point-in-time NWS forecast: <b>{esc(forecast['status'])}</b></p>")
            if forecast["status"] == "available_forecast":
                lines.append(f"<p>NWS grid {esc(forecast['source_id'])} · "
                             f"received {esc(forecast['captured_at'])} · "
                             f"point distance {esc(forecast['distance_km'])} km</p>")
                for name,measurement in forecast["values"].items():
                    lines.append(f"<p>{esc(name)}: {esc(measurement['value'])} "
                                 f"{esc(measurement['unit'])} "
                                 f"({esc(measurement['valid_time'])})</p>")
                lines.append("<p class='muted'>Forecast context, not on-site weather measurement, wildfire probability, or spread estimate.</p>")
        if item["evidence_truncated"]:
            lines.append("<p class='critical'>Only the 100 most recent evidence entries are displayed.</p>")
        lines.append("<table><thead><tr><th>Captured (UTC)</th><th>Source observation</th>"
                     "<th>Type</th><th>Reported status</th><th>Provenance</th></tr></thead><tbody>")
        for row in item["timeline"]:
            url = row["source_url"]
            # Only render trusted schemes as links, while preserving escaped text.
            anchor = (f'<a href="{esc(url)}" rel="noopener noreferrer" target="_blank">Source</a>'
                      if isinstance(url,str) and url.startswith(("https://","http://")) else esc(url))
            lines.append(f"<tr><td>{esc(row['captured_at'])}</td>"
                         f"<td>{esc(row['observed_at'])}</td><td>{esc(row['record_type'])}</td>"
                         f"<td>{esc(row['reported_status'])}</td>"
                         f"<td>{anchor} · {esc(row['source_hash'][:12])}</td></tr>")
        lines.append("</tbody></table></details>")
    lines.append("</section></body></html>")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Offline wildfire source evidence workbench")
    commands = parser.add_subparsers(dest="command",required=True)
    imp = commands.add_parser("import",help="Import checksum-verified downloaded agency receipts")
    imp.add_argument("--db",required=True,type=Path)
    imp.add_argument("--receipts",required=True,type=Path)
    report = commands.add_parser("report",help="Build a read-only decision-time evidence report")
    report.add_argument("--db",required=True,type=Path)
    report.add_argument("--at",required=True)
    report.add_argument("--latitude",type=float)
    report.add_argument("--longitude",type=float)
    report.add_argument("--radius-km",type=float)
    report.add_argument("--limit",type=int,default=200)
    report.add_argument("--satellite-hours",type=int,choices=(6,24,72),default=72)
    report.add_argument("--weather-db",type=Path,help="Optional captured NWS forecast HistoryStore archive")
    report.add_argument("--pixel-db",type=Path,help="Optional verified Release raw FIRMS pixel SQLite archive")
    report.add_argument("--json",type=Path)
    report.add_argument("--html",type=Path)
    report.add_argument("--overwrite",action="store_true")
    compare = commands.add_parser("compare",help="Compare two historical decision-time views")
    compare.add_argument("--db",required=True,type=Path)
    compare.add_argument("--earlier-at",required=True)
    compare.add_argument("--later-at",required=True)
    compare.add_argument("--latitude",type=float)
    compare.add_argument("--longitude",type=float)
    compare.add_argument("--radius-km",type=float)
    compare.add_argument("--limit",type=int,default=200)
    compare.add_argument("--satellite-hours",type=int,choices=(6,24,72),default=72)
    compare.add_argument("--weather-db",type=Path)
    compare.add_argument("--pixel-db",type=Path)
    compare.add_argument("--json",type=Path)
    compare.add_argument("--html",type=Path)
    compare.add_argument("--overwrite",action="store_true")
    args = parser.parse_args()
    if args.command == "import":
        from .history import HistoryStore
        from .receipt_history import import_receipts
        store = HistoryStore(args.db)
        try:
            print(json.dumps(import_receipts(store,args.receipts),sort_keys=True))
        finally:
            store.close()
    else:
        if not args.json and not args.html:
            parser.error("report/compare requires --json and/or --html")
        targets = [p for p in (args.json,args.html) if p is not None]
        if len({p.resolve() for p in targets}) != len(targets):
            parser.error("JSON and HTML output must be different files")
        sources = [args.db] + ([args.weather_db] if args.weather_db else []) + (
            [args.pixel_db] if args.pixel_db else [])
        if any(p.resolve() == src.resolve() for p in targets for src in sources):
            parser.error("reports cannot overwrite any source SQLite archive")
        if any(p.exists() and not p.is_file() for p in targets):
            parser.error("report output must be a regular file")
        if any(p.exists() for p in targets) and not args.overwrite:
            parser.error("output already exists; specify --overwrite to replace")
        if args.command == "report":
            result = build_workbench(args.db,at=args.at,latitude=args.latitude,
                                     longitude=args.longitude,radius_km=args.radius_km,
                                     limit=args.limit,satellite_hours=args.satellite_hours,
                                     weather_db=args.weather_db,pixel_db=args.pixel_db)
            output_html = render_html(result)
        else:
            from .change_explorer import compare_archive, render_changes_html
            result = compare_archive(args.db,earlier_at=args.earlier_at,
                                     later_at=args.later_at,latitude=args.latitude,
                                     longitude=args.longitude,radius_km=args.radius_km,
                                     limit=args.limit,satellite_hours=args.satellite_hours,
                                     weather_db=args.weather_db,pixel_db=args.pixel_db)
            output_html = render_changes_html(result)
        for path,value in ((args.json,json.dumps(result,indent=2,ensure_ascii=False)+"\n"),
                           (args.html,output_html)):
            if path is not None:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(value,encoding="utf-8")
        summary = ({"shown":result["shown"],"truncated":result["truncated"]}
                   if args.command == "report" else
                   {"changed_events":len(result["agency"]["changed_events"]),
                    "comparison_untruncated":result["comparison_untruncated"]})
        print(json.dumps({**summary,"outputs":[str(x) for x in targets]},sort_keys=True))


if __name__ == "__main__":
    main()
