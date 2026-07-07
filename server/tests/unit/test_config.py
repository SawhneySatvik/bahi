"""Config is the provider-swap mechanism — these tests prove env-only selection."""

from __future__ import annotations

import pytest

from bahi.config import Settings


def make_settings(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)


def test_defaults_are_offline_fake(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)
    assert settings.stt_provider == "fake"
    assert settings.tts_provider == "fake"
    assert settings.orchestrator_provider == "fake"
    assert settings.specialist_provider == "fake"
    assert settings.database_url == "sqlite:///bahi.db"


def test_per_role_llm_selection_is_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(
        {
            "BAHI_ORCHESTRATOR_PROVIDER": "google",
            "BAHI_ORCHESTRATOR_MODEL": "gemini-2.5-flash",
            "BAHI_SPECIALIST_PROVIDER": "sarvam",
            "BAHI_SPECIALIST_MODEL": "sarvam-30b",
        },
        monkeypatch,
    )
    assert settings.orchestrator_provider == "google"
    assert settings.orchestrator_model == "gemini-2.5-flash"
    assert settings.specialist_provider == "sarvam"
    assert settings.specialist_model == "sarvam-30b"


def test_language_config_parses_hints_and_codemix(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(
        {"BAHI_LANG_HINTS": " hi , en ,ta", "BAHI_CODEMIX": "false"}, monkeypatch
    )
    lang = settings.language
    assert lang.hints == ("hi", "en", "ta")
    assert lang.codemix is False


def test_api_key_lookup_by_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings({"SARVAM_API_KEY": "sk_test_123"}, monkeypatch)
    assert settings.api_key_for("sarvam") == "sk_test_123"
    assert settings.api_key_for("elevenlabs") is None
    assert settings.api_key_for("nonexistent") is None


def test_profile_summary_never_contains_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings({"SARVAM_API_KEY": "sk_super_secret"}, monkeypatch)
    summary_text = str(settings.profile_summary())
    assert "sk_super_secret" not in summary_text


def test_database_url_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings({"DATABASE_URL": "postgresql://u:p@host/db"}, monkeypatch)
    assert settings.database_url == "postgresql://u:p@host/db"
