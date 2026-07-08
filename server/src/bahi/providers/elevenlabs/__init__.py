"""ElevenLabs adapters — the ONLY modules that may speak ElevenLabs' API shapes.

Verified 2026-07-08 (primary docs): scribe_v2 batch STT ($0.22/hr, scribe_v1
removed 2026-07-09); eleven_flash_v2_5 TTS (~75ms, 32 langs incl. Hindi,
$0.05/1K chars). No documented codemix mode — Scribe auto-detects language;
the codemix flag maps to auto-detection (semantic difference reported in evals).
"""

from __future__ import annotations

BASE_URL = "https://api.elevenlabs.io"

# Premade multilingual voice ("Rachel") — a safe default when the profile
# sets no BAHI_TTS_VOICE; any voice id in the account overrides via env.
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"


def require_key(api_key: str | None) -> str:
    if not api_key:
        raise ValueError(
            "ELEVENLABS_API_KEY is required for provider 'elevenlabs' — set it in .env"
        )
    return api_key
