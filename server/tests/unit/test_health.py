from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bahi.api.app import create_app
from bahi.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_health_reports_resolved_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAHI_STT_PROVIDER", "sarvam")
    monkeypatch.setenv("BAHI_STT_MODEL", "saaras:v3")
    monkeypatch.setenv("BAHI_ORCHESTRATOR_PROVIDER", "google")
    monkeypatch.setenv("BAHI_ORCHESTRATOR_MODEL", "gemini-2.5-flash")

    client = TestClient(create_app())
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["profile"]["stt"] == "sarvam:saaras:v3"
    assert body["profile"]["orchestrator"] == "google:gemini-2.5-flash"
