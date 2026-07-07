"""Deterministic STT fake: returns queued transcripts, else a fixed string."""

from __future__ import annotations

from collections import deque
from typing import Any

from bahi.providers.base import AudioChunk, LanguageConfig, STTUsage, Transcript


class FakeSTT:
    name = "fake"

    def __init__(self, **_: Any) -> None:
        self._queue: deque[str] = deque()

    def enqueue(self, text: str) -> None:
        self._queue.append(text)

    def transcribe(self, audio: AudioChunk, language: LanguageConfig) -> Transcript:
        text = self._queue.popleft() if self._queue else "namaste"
        return Transcript(
            text=text,
            language=language.hints[0] if language.hints else None,
            usage=STTUsage(audio_seconds=max(len(audio.data), 1) / 32000),
        )
