"""Initialize the account-wide Workers subdomain required for Cron deployment."""

import json
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def ensure_workers_subdomain(account: str, token: str) -> str:
    """Preserve an existing subdomain; create one only if the account has none."""
    if not re.fullmatch(r"[a-f0-9]{32}", account) or not token:
        raise ValueError("valid Cloudflare account and deployment token required")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/workers/subdomain"

    def request(method: str, data: bytes | None = None):
        headers = {"Authorization": f"Bearer {token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        with urlopen(Request(url, data=data, headers=headers, method=method), timeout=30) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or payload.get("success") is not True:
            raise RuntimeError("Workers subdomain API did not confirm success")
        return payload.get("result")

    try:
        result = request("GET")
    except HTTPError as exc:
        if exc.code != 404:
            raise
        result = None
    if result is not None:
        if not isinstance(result, dict) or not isinstance(result.get("subdomain"), str) or not result["subdomain"]:
            raise RuntimeError("Workers subdomain API returned an invalid existing value")
        return result["subdomain"]

    name = f"wildfire-signals-{account}"
    created = request("PUT", json.dumps({"subdomain": name}).encode())
    if not isinstance(created, dict) or created.get("subdomain") != name:
        raise RuntimeError("Workers subdomain creation could not be verified")
    return name
