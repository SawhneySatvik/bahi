"""Sarvam adapters — the ONLY modules that may speak Sarvam's API shapes.

Raw REST via httpx (shapes verified live, fixtures in tests/fixtures/sarvam/):
speech uses `api-subscription-key` auth; chat uses `Authorization: Bearer`.
"""

from __future__ import annotations

import httpx

BASE_URL = "https://api.sarvam.ai"

# Core language hints ("hi") -> Sarvam locale codes.
LOCALE = {
    "hi": "hi-IN", "en": "en-IN", "ta": "ta-IN", "te": "te-IN", "kn": "kn-IN",
    "ml": "ml-IN", "mr": "mr-IN", "bn": "bn-IN", "gu": "gu-IN", "pa": "pa-IN",
    "od": "od-IN",
}


def require_key(api_key: str | None) -> str:
    if not api_key:
        raise ValueError("SARVAM_API_KEY is required for provider 'sarvam' — set it in .env")
    return api_key


def raise_readable(resp: httpx.Response, what: str) -> None:
    if resp.status_code >= 400:
        raise RuntimeError(f"Sarvam {what} failed ({resp.status_code}): {resp.text[:500]}")
