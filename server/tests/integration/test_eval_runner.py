"""Offline runner mechanics: a mini-suite through fake providers end-to-end —
given-state seeding, delta capture, JSON payload shape, report rendering."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from bahi.config import get_settings
from bahi.evals.report import render
from bahi.evals.runner import run_suite
from bahi.evals.suite import Suite

MINI_SUITE = {
    "suite": "mini",
    "cases": [
        {
            "id": "chitchat_no_tools",
            "turns": [
                {
                    "utterance": "namaste",
                    "gold_intents_any": ["none"],
                    "expected_ledger_delta": [],
                }
            ],
        },
        {
            "id": "given_state_is_not_a_delta",
            "given": {
                "transactions": [
                    {"type": "udhaar", "customer": "Ramesh", "amount_paise": 20000}
                ]
            },
            "turns": [
                {
                    "utterance": "kuch nahi karna",
                    "gold_intents_any": ["none"],
                    "expected_ledger_delta": [],
                }
            ],
        },
    ],
}


@pytest.fixture(autouse=True)
def fake_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "BAHI_ORCHESTRATOR_PROVIDER",
        "BAHI_SPECIALIST_PROVIDER",
        "BAHI_STT_PROVIDER",
        "BAHI_TTS_PROVIDER",
    ):
        monkeypatch.setenv(var, "fake")
    # run_case() mutates DATABASE_URL directly (CLI semantics); registering it
    # with monkeypatch makes teardown restore the pre-test value.
    monkeypatch.setenv("DATABASE_URL", "sqlite:///eval-runner-test-shield.db")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_runner_end_to_end_offline(tmp_path: Path) -> None:
    suite = Suite.model_validate(MINI_SUITE)
    payload = run_suite(suite, label="offline", repeats=2, results_dir=tmp_path)

    assert payload["suite"] == "mini"
    assert len(payload["runs"]) == 2
    aggregates = payload["runs"][0]["aggregates"]
    # FakeLLM echoes text with no tool calls: chitchat cases pass fully
    assert aggregates["turns"] == 2
    assert aggregates["intent_accuracy"] == 1.0
    assert aggregates["ledger_match"] == 1.0  # given-state seeding is NOT a delta
    assert aggregates["task_success"] == 1.0
    assert list(tmp_path.glob("offline_mini_*.json"))

    markdown = render([payload])
    assert "Intent accuracy" in markdown and "100.0%" in markdown


def test_suite_yaml_on_disk_is_valid() -> None:
    from bahi.evals.suite import load_suite, suite_path

    suite = load_suite(suite_path("core"))
    assert suite.suite == "core"
    assert len(suite.cases) == 40
    turn_count = sum(len(c.turns) for c in suite.cases)
    assert turn_count == 42
    ids = [c.id for c in suite.cases]
    assert len(ids) == len(set(ids)), "case ids must be unique"
    # every YAML case round-trips the schema (pydantic already validated), and
    # every expected write uses positive integer paise
    for case in suite.cases:
        for turn in case.turns:
            for write in turn.expected_ledger_delta:
                assert write.amount_paise > 0


def test_mini_suite_yaml_serializes() -> None:
    # guard: the inline mini suite stays parseable as YAML (docs use it)
    assert yaml.safe_load(yaml.safe_dump(MINI_SUITE))["suite"] == "mini"
