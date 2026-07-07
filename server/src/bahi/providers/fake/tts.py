"""Deterministic TTS fake: emits a valid, silent 16kHz mono WAV."""

from __future__ import annotations

import io
import struct
import wave
from typing import Any

from bahi.providers.base import AudioChunk, Synthesis, TTSUsage

_SAMPLE_RATE = 16000


def _silent_wav(seconds: float = 0.2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SAMPLE_RATE)
        n = int(_SAMPLE_RATE * seconds)
        w.writeframes(struct.pack(f"<{n}h", *([0] * n)))
    return buf.getvalue()


class FakeTTS:
    name = "fake"

    def __init__(self, **_: Any) -> None:
        pass

    def synthesize(self, text: str, language: str, voice_ref: str | None = None) -> Synthesis:
        audio = _silent_wav()
        return Synthesis(
            audio=AudioChunk(data=audio, mime="audio/wav", sample_rate=_SAMPLE_RATE, channels=1),
            usage=TTSUsage(characters=len(text), audio_seconds=0.2),
        )
