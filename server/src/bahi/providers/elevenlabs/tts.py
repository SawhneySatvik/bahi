from __future__ import annotations

from typing import Any

import httpx

from bahi.providers.base import AudioChunk, Synthesis, TTSUsage
from bahi.providers.elevenlabs import BASE_URL, DEFAULT_VOICE_ID, require_key


class ElevenLabsTTS:
    name = "elevenlabs"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        voice: str | None = None,
        transport: httpx.BaseTransport | None = None,
        **_: Any,
    ) -> None:
        self._model = model or "eleven_flash_v2_5"
        self._default_voice = voice or DEFAULT_VOICE_ID
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"xi-api-key": require_key(api_key)},
            timeout=120,
            transport=transport,
        )

    def synthesize(self, text: str, language: str, voice_ref: str | None = None) -> Synthesis:
        voice_id = voice_ref or self._default_voice
        body: dict[str, Any] = {"text": text, "model_id": self._model}
        if self._model == "eleven_flash_v2_5" and language:
            body["language_code"] = language  # flash v2.5 accepts a language pin
        resp = self._client.post(
            f"/v1/text-to-speech/{voice_id}",
            params={"output_format": "mp3_44100_128"},
            json=body,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"ElevenLabs TTS failed ({resp.status_code}): {resp.text[:500]}"
            )
        return Synthesis(
            audio=AudioChunk(data=resp.content, mime="audio/mpeg", sample_rate=44100, channels=1),
            usage=TTSUsage(characters=len(text), audio_seconds=0.0),
            raw={"request_id": resp.headers.get("request-id")},
        )
