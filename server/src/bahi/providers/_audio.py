"""Provider-layer audio helpers (duration estimation for usage accounting)."""

from __future__ import annotations

import contextlib
import io
import wave

from bahi.providers.base import AudioChunk


def estimate_seconds(audio: AudioChunk) -> float:
    """Best-effort duration. WAV parses exactly; raw PCM uses metadata;
    other containers return 0.0 (vendors bill server-side anyway)."""
    if audio.mime.startswith("audio/wav") or audio.data[:4] == b"RIFF":
        with contextlib.suppress(Exception), wave.open(io.BytesIO(audio.data)) as w:
            rate = int(w.getframerate())
            if rate:
                return float(w.getnframes()) / rate
    if audio.sample_rate and audio.mime in ("audio/pcm", "audio/l16"):
        channels = audio.channels or 1
        return len(audio.data) / (audio.sample_rate * 2 * channels)
    return 0.0


def wav_sample_rate(data: bytes) -> int | None:
    with contextlib.suppress(Exception), wave.open(io.BytesIO(data)) as w:
        return int(w.getframerate())
    return None
