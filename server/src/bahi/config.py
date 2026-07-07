"""12-factor configuration: every knob is an env var, nothing else.

Provider selection lives ONLY here. Swapping the whole stack is
`set -a; source envs/<profile>.env; set +a` (or platform env vars) —
never a code edit. Secrets (*_API_KEY) are read by adapters at
construction time via `api_key_for`; they are never logged.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from bahi.providers.base import LanguageConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- capability -> provider selection ---
    stt_provider: str = Field("fake", validation_alias="BAHI_STT_PROVIDER")
    stt_model: str | None = Field(None, validation_alias="BAHI_STT_MODEL")
    tts_provider: str = Field("fake", validation_alias="BAHI_TTS_PROVIDER")
    tts_model: str | None = Field(None, validation_alias="BAHI_TTS_MODEL")
    tts_voice: str | None = Field(None, validation_alias="BAHI_TTS_VOICE")
    vision_provider: str = Field("fake", validation_alias="BAHI_VISION_PROVIDER")
    vision_model: str | None = Field(None, validation_alias="BAHI_VISION_MODEL")

    # --- per-role LLM selection (cross-vendor mixing is first-class) ---
    orchestrator_provider: str = Field("fake", validation_alias="BAHI_ORCHESTRATOR_PROVIDER")
    orchestrator_model: str = Field("fake-orchestrator", validation_alias="BAHI_ORCHESTRATOR_MODEL")
    specialist_provider: str = Field("fake", validation_alias="BAHI_SPECIALIST_PROVIDER")
    specialist_model: str = Field("fake-specialist", validation_alias="BAHI_SPECIALIST_MODEL")

    # --- behavior ---
    routing: str = Field("delegated", validation_alias="BAHI_ROUTING")  # delegated | direct
    lang_hints: str = Field("hi,en", validation_alias="BAHI_LANG_HINTS")
    codemix: bool = Field(True, validation_alias="BAHI_CODEMIX")
    reply_language: str = Field("hi", validation_alias="BAHI_REPLY_LANGUAGE")

    # --- storage ---
    database_url: str = Field(
        "sqlite:///bahi.db",
        validation_alias=AliasChoices("DATABASE_URL", "BAHI_DATABASE_URL"),
    )

    # --- vendor secrets (adapters read these; core never does) ---
    sarvam_api_key: str | None = Field(None, validation_alias="SARVAM_API_KEY")
    elevenlabs_api_key: str | None = Field(None, validation_alias="ELEVENLABS_API_KEY")
    google_api_key: str | None = Field(
        None, validation_alias=AliasChoices("GOOGLE_API_KEY", "GEMINI_API_KEY")
    )
    openai_api_key: str | None = Field(None, validation_alias="OPENAI_API_KEY")

    @property
    def language(self) -> LanguageConfig:
        hints = tuple(h.strip() for h in self.lang_hints.split(",") if h.strip())
        return LanguageConfig(hints=hints or ("hi", "en"), codemix=self.codemix)

    def api_key_for(self, provider: str) -> str | None:
        return {
            "sarvam": self.sarvam_api_key,
            "elevenlabs": self.elevenlabs_api_key,
            "google": self.google_api_key,
            "openai": self.openai_api_key,
        }.get(provider)

    def profile_summary(self) -> dict[str, str]:
        """What /health reports — proves which stack is live, leaks no secrets."""
        return {
            "stt": f"{self.stt_provider}:{self.stt_model or 'default'}",
            "tts": f"{self.tts_provider}:{self.tts_model or 'default'}",
            "orchestrator": f"{self.orchestrator_provider}:{self.orchestrator_model}",
            "specialist": f"{self.specialist_provider}:{self.specialist_model}",
            "vision": f"{self.vision_provider}:{self.vision_model or 'default'}",
            "routing": self.routing,
            "language": f"{self.lang_hints} codemix={self.codemix}",
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
