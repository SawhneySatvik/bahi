from __future__ import annotations

import base64
from typing import Any

import httpx

from bahi.providers._audio import estimate_seconds, wav_sample_rate
from bahi.providers.base import AudioChunk, Synthesis, TTSUsage
from bahi.providers.sarvam import BASE_URL, LOCALE, raise_readable, require_key


class SarvamTTS:
    name = "sarvam"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        voice: str | None = None,
        transport: httpx.BaseTransport | None = None,
        **_: Any,
    ) -> None:
        self._model = model or "bulbul:v3"
        self._default_voice = voice or "priya"  # bulbul:v3 speaker (v2 names differ)
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={"api-subscription-key": require_key(api_key)},
            timeout=60,
            transport=transport,
        )

    def synthesize(self, text: str, language: str, voice_ref: str | None = None) -> Synthesis:
        resp = self._client.post(
            "/text-to-speech",
            json={
                "text": text,
                "model": self._model,
                "speaker": voice_ref or self._default_voice,
                "target_language_code": LOCALE.get(language, language),
            },
        )
        raise_readable(resp, "TTS")
        payload = resp.json()
        audios = payload.get("audios") or []
        data = base64.b64decode(audios[0]) if audios else b""
        audio = AudioChunk(
            data=data,
            mime="audio/wav",  # Bulbul returns WAV (22050 Hz observed live)
            sample_rate=wav_sample_rate(data),
            channels=1,
        )
        return Synthesis(
            audio=audio,
            usage=TTSUsage(characters=len(text), audio_seconds=estimate_seconds(audio)),
            raw={k: v for k, v in payload.items() if k != "audios"},
        )
