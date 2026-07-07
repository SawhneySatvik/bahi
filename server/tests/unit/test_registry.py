from __future__ import annotations

import pytest

from bahi.providers import registry
from bahi.providers.base import (
    LanguageConfig,
    LLMProvider,
    STTProvider,
    TTSProvider,
    VisionProvider,
)


def test_fake_providers_registered_for_all_capabilities() -> None:
    for capability in ("stt", "tts", "llm", "vision"):
        assert "fake" in registry.available(capability)


def test_create_instantiates_protocol_compliant_fakes() -> None:
    assert isinstance(registry.create("stt", "fake"), STTProvider)
    assert isinstance(registry.create("tts", "fake"), TTSProvider)
    assert isinstance(registry.create("llm", "fake"), LLMProvider)
    assert isinstance(registry.create("vision", "fake"), VisionProvider)


def test_unknown_provider_error_lists_available() -> None:
    with pytest.raises(registry.UnknownProviderError) as exc_info:
        registry.create("stt", "definitely-not-a-vendor")
    message = str(exc_info.value)
    assert "definitely-not-a-vendor" in message
    assert "fake" in message  # tells the user what IS available
    assert "BAHI_STT_PROVIDER" in message  # tells the user how to fix it


def test_register_adds_new_provider() -> None:
    registry.register("llm", "_test_dummy", "bahi.providers.fake.llm:FakeLLM")
    try:
        provider = registry.create("llm", "_test_dummy")
        assert isinstance(provider, LLMProvider)
    finally:
        registry._REGISTRY["llm"].pop("_test_dummy", None)


def test_fake_stt_respects_language_hints() -> None:
    stt = registry.create("stt", "fake")
    from bahi.providers.base import AudioChunk

    transcript = stt.transcribe(
        AudioChunk(data=b"\x00" * 320, mime="audio/wav", sample_rate=16000, channels=1),
        LanguageConfig(hints=("ta",), codemix=False),
    )
    assert transcript.language == "ta"
    assert transcript.usage.kind == "stt"
    assert transcript.usage.audio_seconds > 0
