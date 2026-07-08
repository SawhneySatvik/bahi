"""Voice pipeline offline: ffmpeg transcode + fake STT/LLM/TTS through the
real /api/turn/audio endpoint."""

from __future__ import annotations

import base64
import io
import wave
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bahi.api.app import create_app, get_engine, get_voice_loop
from bahi.api.audio import TranscodeError, ffmpeg_available, to_canonical_wav
from bahi.config import get_settings
from bahi.providers.fake.tts import _silent_wav

pytestmark = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/voice.db")
    for var in (
        "BAHI_ORCHESTRATOR_PROVIDER",
        "BAHI_SPECIALIST_PROVIDER",
        "BAHI_STT_PROVIDER",
        "BAHI_TTS_PROVIDER",
    ):
        monkeypatch.setenv(var, "fake")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_voice_loop.cache_clear()
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_voice_loop.cache_clear()


def test_transcode_produces_canonical_wav() -> None:
    chunk = to_canonical_wav(_silent_wav(0.3), "audio/wav")
    assert chunk.mime == "audio/wav"
    assert chunk.sample_rate == 16000
    with wave.open(io.BytesIO(chunk.data)) as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1


def test_transcode_finalizes_riff_header() -> None:
    # A piped ffmpeg WAV carries the 0xFFFFFFFF streaming size sentinel, which
    # Sarvam's billing precheck priced as a multi-GB file -> 402 (found live).
    import struct

    chunk = to_canonical_wav(_silent_wav(0.3), "audio/wav")
    riff_size = struct.unpack("<I", chunk.data[4:8])[0]
    assert riff_size == len(chunk.data) - 8


def test_transcode_rejects_garbage() -> None:
    with pytest.raises(TranscodeError):
        to_canonical_wav(b"definitely not audio", "application/octet-stream")


def test_voice_endpoint_full_loop_offline(client: TestClient) -> None:
    response = client.post(
        "/api/turn/audio", files={"file": ("mic.wav", _silent_wav(0.3), "audio/wav")}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "namaste"  # FakeSTT default
    assert body["reply"]
    assert body["stt_seconds"] >= 0 and body["tts_seconds"] >= 0
    audio = base64.b64decode(body["reply_audio_b64"])
    assert audio[:4] == b"RIFF"  # FakeTTS emits WAV
    kinds = {event["kind"] for event in body["trace"]}
    assert {"stt", "llm", "tts"} <= kinds


def test_voice_endpoint_rejects_oversize(client: TestClient) -> None:
    big = b"\x00" * 4_000_001
    response = client.post("/api/turn/audio", files={"file": ("big.wav", big, "audio/wav")})
    assert response.status_code == 413
