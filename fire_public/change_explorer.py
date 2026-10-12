"""Offline historical evidence change explorer.

Compares what was *known to the archive* at two decision times. Changes in
agency layer presence, satellite candidate counts or weather forecasts are
not evidence of wildfire start, growth, containment or extinguishment.
"""
from __future__ import annotations

import html
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from .history import _timestamp
from .intelligence_workbench import build_workbench

MAX_CHANGED_EVENTS = 500


def _same_scope(a: dict, b: dict) -> None:
    if a["scope"] != b["scope"]:
        raise ValueError("Both as-of reports must have the same geographical scope")
    if a["satellite_evidence"]["window_hours"] != b["satellite_evidence"]["window_hours"]:
        raise ValueError("Both satellite windows must have equal duration")


def _event_diff(before: dict | None, after: dict | None) -> dict:
    # Both events are independently provider-identified, never proximity matched.
    representative = after if after is not None else before
    old_ids = {x["source_hash"] for x in before["timeline"]} if before else set()
    new_rows = [x for x in after["timeline"] if x["source_hash"] not in old_ids] if after else []
    status_before = before["reported_status"] if before else None
    status_after = after["reported_status"] if after else None
    old_layer = before["source_layer_availability"] if before else "not_known_to_archive"
    new_layer = after["source_layer_availability"] if after else "not_in_comparison_sample"
    if before is None:
        kind = "first_seen_in_archive"
    elif after is None:
        kind = "out_of_scope_or_missing_from_result"
    elif status_before != status_after:
        kind = "source_reported_status_changed"
    elif old_layer != new_layer:
        kind = "source_layer_availability_changed"
    elif new_rows:
        kind = "additional_archive_evidence"
    else:
        kind = "no_reported_change"
    return {
        "event_id": representative["event_id"], "provider": representative["provider"],
        "official_id": representative["official_id"], "name": representative["name"],
        "change_type": kind, "reported_status_before": status_before,
        "reported_status_after": status_after,
        "layer_availability_before": old_layer,
        "layer_availability_after": new_layer,
        "new_evidence_records_in_displayed_timeline": len(new_rows),
        "new_evidence": new_rows,
        "first_captured_at": representative["first_captured_at"],
        "note": "Reported layer/history change, not independently verified fire activity or outcome.",
    }


def compare_reports(before: dict, after: dict) -> dict:
    """Pure comparison of two individually validated decision-time workbench reports.

    Comparisons are explicitly flagged as incomplete when the event cohorts or
    observation queries have hit their display caps, or when timelines are truncated.
    """
    first, second = _timestamp(before["decision_at"]), _timestamp(after["decision_at"])
    if first >= second:
        raise ValueError("before must be strictly earlier than after")
    _same_scope(before, after)
    past = {x["event_id"]: x for x in before["incidents"]}
    current = {x["event_id"]: x for x in after["incidents"]}
    identifiers = sorted(past.keys() | current.keys())
    if len(identifiers) > MAX_CHANGED_EVENTS:
        raise ValueError("Comparison exceeds safe report cap")
    differences = [_event_diff(past.get(k), current.get(k)) for k in identifiers]
    changed = [x for x in differences if x["change_type"] != "no_reported_change"]
    sat_before = before["satellite_evidence"]
    sat_after = after["satellite_evidence"]

    weather_changes = []
    for key in sorted(past.keys() & current.keys()):
        former = past[key].get("weather_context")
        latter = current[key].get("weather_context")
        if former is None and latter is None:
            continue
        if former is None or latter is None:
            continue  # no coverage comparison when only one report has weather enabled
        keys = ("status","evidence_id","captured_at","source_id")
        if any(former.get(k) != latter.get(k) for k in keys):
            weather_changes.append({
                "event_id":key,"name":current[key]["name"],
                "before":{k:former.get(k) for k in keys},
                "after":{k:latter.get(k) for k in keys},
                "note":"Different issued/valid-time forecasts are NOT measurements of actual weather change.",
            })

    states = {}
    for provider in sorted(before["source_states"].keys() | after["source_states"].keys()):
        older = before["source_states"].get(provider, {})
        newer = after["source_states"].get(provider, {})
        states[provider] = {
            "before": older.get("status", "unknown"), "after": newer.get("status","unknown"),
            "before_scan_at":older.get("scan_at"),"after_scan_at":newer.get("scan_at"),
            "changed":older.get("status") != newer.get("status"),
        }
    incomplete_reasons = []
    if before["truncated"] or after["truncated"]:
        incomplete_reasons.append("agency_display_limit")
    if sat_before["row_limit_reached"] or sat_after["row_limit_reached"]:
        incomplete_reasons.append("satellite_archive_query_limit")
    if any(x.get("evidence_truncated") for x in before["incidents"]+after["incidents"]):
        incomplete_reasons.append("agency_evidence_timeline_limit")
    for report in (before,after):
        weather = report.get("weather_evidence")
        if weather and weather["archive_row_limit_reached"]:
            incomplete_reasons.append("weather_archive_query_limit")
            break

    return {
        "schema_version":1,
        "earlier_at":first,"later_at":second,
        "hours_between":round((datetime.fromisoformat(second) -
                               datetime.fromisoformat(first)).total_seconds()/3600,3),
        "scope":before["scope"],
        "comparison_untruncated":not incomplete_reasons,
        "incomplete_reasons":sorted(set(incomplete_reasons)),
        "agency": {
            "earlier_matched":before["matched_identities"],
            "later_matched":after["matched_identities"],
            "earlier_shown":before["shown"],"later_shown":after["shown"],
            "change_counts":dict(sorted(Counter(x["change_type"] for x in differences).items())),
            "changed_events":changed,
            "unchanged_in_displayed_cohort":len(differences)-len(changed),
        },
        "sources":states,
        "satellite": {
            "earlier":{k:sat_before[k] for k in
                       ("available_archive_records","distinct_observed_cells",
                        "cells_observed_in_multiple_hours","row_limit_reached")},
            "later":{k:sat_after[k] for k in
                     ("available_archive_records","distinct_observed_cells",
                      "cells_observed_in_multiple_hours","row_limit_reached")},
            "window_hours":sat_before["window_hours"],
            "note":"Two rolling windows of available thermal candidates, NOT burned-area, ignition or spread measurements.",
        },
        "forecast_receipt_changes":weather_changes,
        "warnings":[
            "Known-at-time comparison only: later-collected historical records did not exist in the earlier archive view.",
            "An incident newly seen here may predate the earlier decision time.",
            "Absent from active agency layers never means extinguished; source failure does not mean zero fires.",
            "A change in observed thermal candidates or weather forecasts cannot estimate wildfire growth or forecast skill.",
            "Truncated data may hide changes; a clean comparison requires untruncated reports and audited collection coverage.",
        ],
        "wildfire_outcome_labels_created":0,
        "validated_prediction":False,
    }


def compare_archive(path: str | Path, *, earlier_at: str, later_at: str,
                    latitude: float | None = None, longitude: float | None = None,
                    radius_km: float | None = None, limit: int = 200,
                    satellite_hours: int = 72, weather_db: str | Path | None = None) -> dict:
    kwargs = dict(latitude=latitude,longitude=longitude,radius_km=radius_km,
                  limit=limit,satellite_hours=satellite_hours,weather_db=weather_db)
    before = build_workbench(path,at=earlier_at,**kwargs)
    after = build_workbench(path,at=later_at,**kwargs)
    return compare_reports(before,after)


def render_changes_html(result: dict) -> str:
    """Responsive standalone HTML; source strings always escaped, no JavaScript."""
    esc=lambda value:html.escape(str(value),quote=True)
    output=["""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wildfire Signals | Evidence Change Explorer</title>
<style>
:root{font-family:system-ui,sans-serif;background:#111c26;color:#edf3f4}
body{max-width:1100px;margin:auto;padding:24px;line-height:1.5}
h1{font-size:1.7rem}h2{font-size:1.15rem}small,.quiet{color:#bed1d8}
header,section,details{background:#1b303d;padding:15px;border-radius:10px;
border:1px solid #3b5964;margin-bottom:13px}
table{border-collapse:collapse;width:100%;font-size:.85rem}
th,td{border-bottom:1px solid #355262;text-align:left;padding:7px;vertical-align:top;overflow-wrap:anywhere}
th{color:#bed1d8}summary{cursor:pointer;font-weight:650}
.warning{color:#ffd49f}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:9px}
.grid article{background:#294451;border-radius:8px;padding:9px}
.grid strong{font-size:1.5rem;display:block}
@media(max-width:650px){body{padding:10px}table{font-size:.7rem}}
</style></head><body>"""]
    output.append(f"<header><h1>Historical Evidence Change Explorer</h1>"
                  f"<p>Earlier: <b>{esc(result['earlier_at'])}</b> · "
                  f"Later: <b>{esc(result['later_at'])}</b></p>"
                  f"<p class='warning'>This compares evidence available to the archive, "
                  f"not verified wildfire growth or extinguishment.</p></header>")
    output.append("<section><h2>Agency evidence comparison</h2><div class='grid'>")
    for label,num in (("Before",result["agency"]["earlier_matched"]),
                      ("After",result["agency"]["later_matched"]),
                      ("Changed within displayed sample",len(result["agency"]["changed_events"])),
                      ("Hours between",result["hours_between"])):
        output.append(f"<article><strong>{esc(num)}</strong>{esc(label)}</article>")
    output.append("</div>")
    if not result["comparison_untruncated"]:
        output.append(f"<p class='warning'>Incomplete comparison: "
                      f"{esc(', '.join(result['incomplete_reasons']))}</p>")
    for event in result["agency"]["changed_events"]:
        output.append(f"<details><summary>{esc(event['provider'])} · {esc(event['name'])} "
                      f"— {esc(event['change_type'])}</summary>"
                      f"<p>Agency identity: {esc(event['official_id'])}</p>"
                      f"<p>Reported status: {esc(event['reported_status_before'])} → "
                      f"{esc(event['reported_status_after'])}</p>"
                      f"<p>Source-layer availability: {esc(event['layer_availability_before'])} → "
                      f"{esc(event['layer_availability_after'])}</p>"
                      f"<p>New displayed evidence rows: "
                      f"{esc(event['new_evidence_records_in_displayed_timeline'])}</p>")
        for row in event["new_evidence"]:
            output.append(f"<p><small>{esc(row['captured_at'])} · "
                          f"{esc(row['record_type'])} · {esc(row['source_hash'][:14])}</small></p>")
        output.append("</details>")
    if not result["agency"]["changed_events"]:
        output.append("<p>No changes among the displayed archived agency evidence.</p>")
    output.append("</section><section><h2>Satellite thermal candidates (separate evidence)</h2>")
    output.append(f"<p>Rolling {esc(result['satellite']['window_hours'])}-hour windows. "
                  f"{esc(result['satellite']['note'])}</p>")
    output.append("<table><thead><tr><th>Measure</th><th>Earlier</th><th>Later</th></tr></thead><tbody>")
    for k in ("available_archive_records","distinct_observed_cells",
              "cells_observed_in_multiple_hours"):
        output.append(f"<tr><td>{esc(k.replace('_',' '))}</td>"
                      f"<td>{esc(result['satellite']['earlier'][k])}</td>"
                      f"<td>{esc(result['satellite']['later'][k])}</td></tr>")
    output.append("</tbody></table></section><section><h2>Source collection states</h2><ul>")
    for source,row in result["sources"].items():
        output.append(f"<li><b>{esc(source)}</b>: {esc(row['before'])} → {esc(row['after'])}</li>")
    output.append("</ul>")
    if result["forecast_receipt_changes"]:
        output.append("<h2>Changed captured forecast receipts</h2><ul>")
        for row in result["forecast_receipt_changes"]:
            output.append(f"<li>{esc(row['name'])}: "
                          f"{esc(row['before']['captured_at'])} → "
                          f"{esc(row['after']['captured_at'])}</li>")
        output.append("</ul>")
    for warning in result["warnings"]:
        output.append(f"<p class='quiet'>{esc(warning)}</p>")
    output.append("</section></body></html>")
    return "\n".join(output)
