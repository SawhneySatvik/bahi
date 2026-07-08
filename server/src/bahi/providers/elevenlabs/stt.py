from __future__ import annotations

from typing import Any

import httpx

from bahi.providers._audio import estimate_seconds
from bahi.providers.base import AudioChunk, LanguageConfig, STTUsage, Transcript
from bahi.providers.elevenlabs import BASE_URL, require_key


class ElevenLabsSTT:
    name = "elevenlabs"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
        **_: Any,
    ) -> None:
        self._model = model or "scribe_v2"
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"xi-api-key": require_key(api_key)},
            timeout=120,
            transport=transport,
        )

    def transcribe(self, audio: AudioChunk, language: LanguageConfig) -> Transcript:
        # Scribe has no codemix mode: language auto-detection (incl. mid-speech
        # switching) is the closest concept, so we send no language pin when
        # codemix is on; a single non-codemix hint is passed through.
        data: dict[str, str] = {"model_id": self._model}
        if not language.codemix and language.hints:
            data["language_code"] = language.hints[0]
        resp = self._client.post(
            "/v1/speech-to-text",
            files={"file": ("utterance.wav", audio.data, audio.mime)},
            data=data,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"ElevenLabs STT failed ({resp.status_code}): {resp.text[:500]}"
            )
        payload = resp.json()
        return Transcript(
            text=payload.get("text", ""),
            language=payload.get("language_code"),
            usage=STTUsage(audio_seconds=estimate_seconds(audio)),
            raw=payload,
        )
