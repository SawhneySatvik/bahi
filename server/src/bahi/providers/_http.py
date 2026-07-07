"""Provider-layer HTTP resilience: retry on rate limits / transient 5xx.

Free-tier LLM quotas are tight (observed live: Gemini free tier = 5 req/min
with 'retry in Ns' in the 429 body) — eval runs would collapse without this.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

RETRYABLE = {429, 500, 502, 503}
MAX_SLEEP_SECONDS = 65.0

_RETRY_IN = re.compile(r"retry in ([0-9.]+)\s*s", re.IGNORECASE)


def _suggested_delay(resp: httpx.Response, fallback: float) -> float:
    header = resp.headers.get("retry-after")
    if header and header.replace(".", "", 1).isdigit():
        return float(header)
    match = _RETRY_IN.search(resp.text)
    if match:
        return float(match.group(1)) + 1.0
    return fallback


def post_with_retry(
    client: httpx.Client,
    url: str,
    *,
    json_body: dict[str, Any],
    retries: int = 3,
) -> httpx.Response:
    delay = 2.0
    for attempt in range(retries + 1):
        resp = client.post(url, json=json_body)
        if resp.status_code not in RETRYABLE or attempt == retries:
            return resp
        time.sleep(min(_suggested_delay(resp, delay), MAX_SLEEP_SECONDS))
        delay *= 3
    return resp
