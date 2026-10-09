"""GitHub workflow guard with an automatic seven-day stop."""
import os
from datetime import datetime, timezone
from pathlib import Path


def state(now, start, end):
    now, start, end = (datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(timezone.utc)
                       for x in (now, start, end))
    if not start < end:
        raise ValueError("pilot window invalid")
    return {"active":str(start <= now < end).lower(), "expired":str(now >= end).lower()}


def main():
    now = datetime.now(timezone.utc).isoformat()
    result = state(now, os.environ["PILOT_START_UTC"], os.environ["PILOT_END_UTC"])
    with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
        for key, value in result.items():
            output.write(f"{key}={value}\n")


if __name__ == "__main__":
    main()
