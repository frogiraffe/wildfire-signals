"""Read-only interval ledger for the seven-day GitHub Actions source pilot."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .pilot_window import PILOT_END_UTC, PILOT_START_UTC

SCHEDULE_GRACE = timedelta(hours=2)


def _utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone-aware run timestamp required")
    return parsed.astimezone(timezone.utc)


def audit(runs, *, until=None):
    start, end = _utc(PILOT_START_UTC), _utc(PILOT_END_UTC)
    checked_at = _utc(until) if until else datetime.now(timezone.utc)
    assessment_end = min(end, checked_at - SCHEDULE_GRACE)
    first_tick = start.replace(minute=37, second=0, microsecond=0)
    if first_tick < start:
        first_tick += timedelta(hours=1)
    slots = {}
    tick = first_tick
    while tick < assessment_end:
        slots[tick.isoformat()] = []
        tick += timedelta(hours=1)
    for run in runs:
        if run.get("event") != "schedule":
            continue
        created = _utc(run["createdAt"])
        tick = created.replace(minute=37, second=0, microsecond=0)
        if tick > created:
            tick -= timedelta(hours=1)
        if tick.isoformat() in slots:
            slots[tick.isoformat()].append(run)
    missing, failed, pending, successful = [], [], [], 0
    for tick, records in slots.items():
        if not records:
            missing.append(tick)
        elif any(row.get("conclusion") == "success" for row in records):
            successful += 1
        elif any(row.get("status") != "completed" for row in records):
            pending.append(tick)
        else:
            failed.append(tick)
    return {"expected_intervals":len(slots), "successful_intervals":successful,
            "missing_intervals":missing, "failed_intervals":failed,
            "pending_intervals":pending,
            "complete_window":checked_at >= end + SCHEDULE_GRACE}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m fire_public.pilot_audit RUNS_JSON")
    runs = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    print(json.dumps(audit(runs), sort_keys=True))


if __name__ == "__main__":
    main()
