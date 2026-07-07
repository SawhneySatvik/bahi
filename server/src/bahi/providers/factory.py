"""Composition root: Settings -> live providers. The ONLY place selection
happens; everything downstream holds a Protocol and cannot tell vendors apart."""

from __future__ import annotations

from typing import Literal

from bahi.config import Settings
from bahi.providers import registry
from bahi.providers.base import LLMProvider, STTProvider, TTSProvider, VisionProvider

LLMRole = Literal["orchestrator", "specialist"]


def build_stt(settings: Settings) -> STTProvider:
    provider: STTProvider = registry.create(
        "stt",
        settings.stt_provider,
        api_key=settings.api_key_for(settings.stt_provider),
        model=settings.stt_model,
    )
    return provider


def build_tts(settings: Settings) -> TTSProvider:
    provider: TTSProvider = registry.create(
        "tts",
        settings.tts_provider,
        api_key=settings.api_key_for(settings.tts_provider),
        model=settings.tts_model,
        voice=settings.tts_voice,
    )
    return provider


def build_llm(settings: Settings, role: LLMRole) -> tuple[LLMProvider, str]:
    """Returns (provider, model) for the role — provider AND model are
    per-role env vars, so cross-vendor mixing needs no code."""
    name = (
        settings.orchestrator_provider if role == "orchestrator" else settings.specialist_provider
    )
    model = settings.orchestrator_model if role == "orchestrator" else settings.specialist_model
    provider: LLMProvider = registry.create("llm", name, api_key=settings.api_key_for(name))
    return provider, model


def build_vision(settings: Settings) -> VisionProvider:
    provider: VisionProvider = registry.create(
        "vision",
        settings.vision_provider,
        api_key=settings.api_key_for(settings.vision_provider),
        model=settings.vision_model,
    )
    return provider
