"""Read-only CWFIS source-status interval analysis, not fire outcome inference."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .decision_evidence import _open_readonly
from .history import _timestamp

STATUSES = {"OC", "BH", "UC"}


def analyze_status_series(db_path: Path, source_id: str, *, as_of: str) -> dict:
    if not source_id:
        raise ValueError("CWFIS source id required")
    cutoff = _timestamp(as_of)
    with closing(_open_readonly(Path(db_path))) as connection:
        versions = connection.execute("""
            SELECT id, observed_at, captured_at, payload_json
            FROM observations
            WHERE subject_kind = 'agency_incident' AND provider = 'cwfis'
              AND source_id = ? AND record_type = 'incident_status'
              AND observed_at <= ? AND captured_at <= ?
            ORDER BY observed_at, captured_at, id
        """, (source_id, cutoff, cutoff)).fetchall()
    same_receipt = {}
    latest_by_start = {}
    for row in versions:
        key = row["observed_at"], row["captured_at"]
        previous = same_receipt.get(key)
        if previous is not None and previous != row["payload_json"]:
            raise ValueError("ambiguous CWFIS versions at the same receipt time")
        same_receipt[key] = row["payload_json"]
        latest_by_start[row["observed_at"]] = row
    intervals = []
    for start_at, row in sorted(latest_by_start.items()):
        payload = json.loads(row["payload_json"])
        status = payload.get("stage_of_control_status")
        if status not in STATUSES:
            raise ValueError("invalid CWFIS source status")
        end_at = _timestamp(payload["record_end"]) if payload.get("record_end") else None
        if end_at is not None and end_at <= start_at:
            raise ValueError("invalid CWFIS source interval")
        hours = ((datetime.fromisoformat(end_at) - datetime.fromisoformat(start_at))
                 .total_seconds() / 3600) if end_at else None
        intervals.append({"start_at": start_at, "end_at": end_at,
                          "status": status, "captured_at": row["captured_at"],
                          "source_record_id": row["id"],
                          "interval_hours": round(hours, 3) if hours is not None else None})
    transitions, gaps, overlaps = [], [], []
    by_status = defaultdict(float)
    for index, current in enumerate(intervals):
        if current["interval_hours"] is not None:
            by_status[current["status"]] += current["interval_hours"]
        if index == 0:
            continue
        previous = intervals[index - 1]
        if previous["status"] != current["status"]:
            transitions.append({"at": current["start_at"], "from": previous["status"],
                                "to": current["status"]})
        if previous["end_at"]:
            seconds = ((datetime.fromisoformat(current["start_at"]) -
                        datetime.fromisoformat(previous["end_at"])).total_seconds())
            if seconds > 0:
                gaps.append({"from": previous["end_at"], "to": current["start_at"],
                             "hours": round(seconds / 3600, 3)})
            elif seconds < 0:
                overlaps.append({"from": current["start_at"], "to": previous["end_at"],
                                 "hours": round(-seconds / 3600, 3)})
    ends = [datetime.fromisoformat(row["end_at"]) for row in intervals if row["end_at"]]
    captures = [datetime.fromisoformat(row["captured_at"]) for row in intervals]
    final_end = intervals[-1]["end_at"] if intervals else None
    return {"schema_version": 1, "source": f"cwfis:{source_id}", "as_of": cutoff,
            "source_version_count": len(versions), "record_count": len(intervals),
            "intervals": intervals, "transitions": transitions,
            "transition_count": len(transitions),
            "control_to_out_of_control_count": sum(row["to"] == "OC" and
                row["from"] in {"BH", "UC"} for row in transitions),
            "interval_hours_by_status": {key: round(value, 3)
                                          for key, value in sorted(by_status.items())},
            "gaps": gaps, "overlaps": overlaps,
            "retrospective_capture_only": bool(intervals and len(ends) == len(intervals)
                                               and min(captures) > max(ends)),
            "current_state_unknown": (not final_end or final_end <= cutoff),
            "prediction": None, "extinguishment_label": None}


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only CWFIS source-status timeline")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--as-of", required=True)
    args = parser.parse_args()
    print(json.dumps(analyze_status_series(args.db,args.source_id,as_of=args.as_of),
                     sort_keys=True))


if __name__ == "__main__":
    main()
