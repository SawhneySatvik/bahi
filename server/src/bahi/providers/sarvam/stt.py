from __future__ import annotations

from typing import Any

import httpx

from bahi.providers._audio import estimate_seconds
from bahi.providers.base import AudioChunk, LanguageConfig, STTUsage, Transcript
from bahi.providers.sarvam import BASE_URL, raise_readable, require_key


class SarvamSTT:
    name = "sarvam"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        transport: httpx.BaseTransport | None = None,
        **_: Any,
    ) -> None:
        self._model = model or "saaras:v3"
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"api-subscription-key": require_key(api_key)},
            timeout=60,
            transport=transport,
        )

    def transcribe(self, audio: AudioChunk, language: LanguageConfig) -> Transcript:
        # `codemix` is Saaras's native mixed-language mode — the core never
        # sees this vendor term, it only sets LanguageConfig.codemix.
        mode = "codemix" if language.codemix else "transcribe"
        resp = self._client.post(
            "/speech-to-text",
            files={"file": ("utterance.wav", audio.data, audio.mime)},
            data={"model": self._model, "mode": mode},
        )
        raise_readable(resp, "STT")
        payload = resp.json()
        return Transcript(
            text=payload.get("transcript", ""),
            language=payload.get("language_code"),
            usage=STTUsage(audio_seconds=estimate_seconds(audio)),
            raw=payload,
        )
