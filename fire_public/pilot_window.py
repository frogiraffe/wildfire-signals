"""GitHub workflow guard with an automatic seven-day stop."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path


PILOT_START_UTC = "2026-10-09T18:18:03Z"
PILOT_END_UTC = "2026-10-16T18:18:03Z"


def state(now, start=PILOT_START_UTC, end=PILOT_END_UTC):
    now, start, end = (datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(timezone.utc)
                       for x in (now, start, end))
    if not start < end <= start + timedelta(days=7):
        raise ValueError("pilot window invalid")
    return {"active":str(start <= now < end).lower(), "expired":str(now >= end).lower()}


def main():
    now = datetime.now(timezone.utc).isoformat()
    result = state(now)
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for key, value in result.items():
            output.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
