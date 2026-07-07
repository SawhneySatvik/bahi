"""Cost accounting in INR. Prices are vendor-published (verified 2026-07-08);
USD prices convert at a PINNED rate printed in every report — cross-currency
comparisons are meaningless without stating the assumption.
"""

from __future__ import annotations

FX_INR_PER_USD = 90.0  # pinned 2026-07-08; update deliberately, never silently
PRICES_DATED = "2026-07-08"

# model -> (INR per 1M input tokens, INR per 1M output tokens)
LLM_PRICES_INR_PER_MTOK: dict[str, tuple[float, float]] = {
    "sarvam-105b": (4.0, 16.0),
    "sarvam-30b": (2.5, 10.0),
    "gemini-2.5-flash": (0.30 * FX_INR_PER_USD, 2.50 * FX_INR_PER_USD),
    "gemini-2.5-flash-lite": (0.10 * FX_INR_PER_USD, 0.40 * FX_INR_PER_USD),
    "gpt-5.4-mini": (0.75 * FX_INR_PER_USD, 4.50 * FX_INR_PER_USD),
    "gpt-5.4-nano": (0.20 * FX_INR_PER_USD, 1.25 * FX_INR_PER_USD),
}

# provider -> INR per audio-second
STT_PRICES_INR_PER_SECOND: dict[str, float] = {
    "sarvam": 45.0 / 3600,  # ₹45/hour
    "elevenlabs": 0.22 * FX_INR_PER_USD / 3600,  # $0.22/hour (scribe_v2 batch)
}

# provider -> INR per character
TTS_PRICES_INR_PER_CHAR: dict[str, float] = {
    "sarvam": 0.0,  # billed per audio-second instead, see below
    "elevenlabs": 0.05 * FX_INR_PER_USD / 1000,  # $0.05 / 1K chars (flash v2.5)
}

TTS_PRICES_INR_PER_SECOND: dict[str, float] = {
    "sarvam": 45.0 / 3600,  # ₹45/hour of generated audio
    "elevenlabs": 0.0,
}


def _normalize_model(model: str) -> str:
    # strip date/version suffixes like "gemini-2.5-flash-001"
    for known in LLM_PRICES_INR_PER_MTOK:
        if model.startswith(known):
            return known
    return model


def llm_cost_inr(model: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = LLM_PRICES_INR_PER_MTOK.get(_normalize_model(model))
    if prices is None:
        return None  # unknown model: report as unpriced, never silently zero
    per_in, per_out = prices
    return (input_tokens * per_in + output_tokens * per_out) / 1_000_000


def stt_cost_inr(provider: str, audio_seconds: float) -> float | None:
    rate = STT_PRICES_INR_PER_SECOND.get(provider)
    return None if rate is None else audio_seconds * rate


def tts_cost_inr(provider: str, characters: int, audio_seconds: float) -> float | None:
    per_char = TTS_PRICES_INR_PER_CHAR.get(provider)
    per_sec = TTS_PRICES_INR_PER_SECOND.get(provider)
    if per_char is None or per_sec is None:
        return None
    return characters * per_char + audio_seconds * per_sec
