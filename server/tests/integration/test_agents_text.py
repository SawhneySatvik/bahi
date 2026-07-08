"""Agent-loop integration tests: scripted FakeLLMs drive real tools against a
real (temp) database — the whole turn minus the network."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import select

from bahi.config import get_settings
from bahi.core.orchestrator import TurnEngine
from bahi.ledger.db import _engines, get_engine, init_db, session_scope
from bahi.ledger.models import Transaction
from bahi.mcp_server.tools import ledger_tool_registry
from bahi.providers.base import AssistantTurn, LLMUsage, ToolCall
from bahi.providers.fake.llm import FakeLLM


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = f"sqlite:///{tmp_path}/agents.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    init_db(get_engine(url))
    yield url
    get_settings.cache_clear()
    _engines.clear()


def _engine_with(
    orchestrator: FakeLLM, specialist: FakeLLM, routing: str = "delegated"
) -> TurnEngine:
    return TurnEngine(
        orchestrator_llm=orchestrator,
        orchestrator_model="fake-orchestrator",
        specialist_llm=specialist,
        specialist_model="fake-specialist",
        registry=ledger_tool_registry(),
        routing=routing,
    )


def _transactions() -> list[Transaction]:
    with session_scope() as session:
        return list(session.scalars(select(Transaction)))


def test_delegated_udhaar_flow_mutates_ledger(db: str) -> None:
    orchestrator = FakeLLM()
    orchestrator.enqueue_tool_call(
        "delegate_khata", {"instruction": "Ramesh ko 200 rupaye udhaar likho"}
    )
    orchestrator.enqueue_text("Ramesh ka 200 rupaye udhaar likh diya.")
    specialist = FakeLLM()
    specialist.enqueue_tool_call(
        "add_udhaar", {"customer_name": "Ramesh", "amount_paise": 20000}
    )
    specialist.enqueue_text("Udhaar record ho gaya, naya balance ₹200.")

    result = _engine_with(orchestrator, specialist).run_text_turn(
        "Ramesh ko 200 rupaye udhaar likh do"
    )

    txns = _transactions()
    assert [(t.type, t.amount_paise) for t in txns] == [("udhaar", 20000)]
    assert result.intents == ["khata"]
    assert result.reply == "Ramesh ka 200 rupaye udhaar likh diya."
    assert result.completed
    kinds = [e.kind for e in result.events]
    assert "delegate" in kinds and "tool" in kinds and "llm" in kinds
    # specialist saw the original utterance for context
    specialist_user = specialist.calls[0]["messages"][1].content
    assert "Ramesh ko 200 rupaye udhaar likh do" in specialist_user


def test_multi_intent_turn_runs_two_specialists(db: str) -> None:
    orchestrator = FakeLLM()
    orchestrator.enqueue(
        AssistantTurn(
            content=None,
            tool_calls=(
                ToolCall(
                    id="c1", name="delegate_billing", arguments={"instruction": "150 ki sale"}
                ),
                ToolCall(
                    id="c2",
                    name="delegate_khata",
                    arguments={"instruction": "Suresh ko 100 udhaar"},
                ),
            ),
            usage=LLMUsage(),
            model="fake",
        )
    )
    orchestrator.enqueue_text("Sale aur udhaar dono likh diye.")
    specialist = FakeLLM()
    specialist.enqueue_tool_call("add_sale", {"amount_paise": 15000})
    specialist.enqueue_text("₹150 ki sale record ki.")
    specialist.enqueue_tool_call("add_udhaar", {"customer_name": "Suresh", "amount_paise": 10000})
    specialist.enqueue_text("Suresh ka ₹100 udhaar likha.")

    result = _engine_with(orchestrator, specialist).run_text_turn(
        "150 ki sale likho aur Suresh ko 100 udhaar"
    )

    txns = {(t.type, t.amount_paise) for t in _transactions()}
    assert txns == {("sale", 15000), ("udhaar", 10000)}
    assert result.intents == ["billing", "khata"]


def test_specialist_recovers_from_tool_error(db: str) -> None:
    orchestrator = FakeLLM()
    orchestrator.enqueue_tool_call("delegate_khata", {"instruction": "Ghost se 500 wapas aaye"})
    orchestrator.enqueue_text("Ghost naam ka koi customer nahi mila.")
    specialist = FakeLLM()
    specialist.enqueue_tool_call(
        "record_repayment", {"customer_name": "Ghost", "amount_paise": 50000}
    )
    specialist.enqueue_text("Ghost naam ka customer ledger mein nahi hai.")

    result = _engine_with(orchestrator, specialist).run_text_turn("Ghost ne 500 wapas kiye")

    assert _transactions() == []
    assert result.completed
    # the error surfaced to the specialist as a tool result, not an exception
    repayment_event = next(e for e in result.events if e.label.endswith("record_repayment"))
    assert "error" in repayment_event.detail["result"]


def test_direct_routing_single_hop(db: str) -> None:
    orchestrator = FakeLLM()
    orchestrator.enqueue_tool_call("add_sale", {"amount_paise": 15000})
    orchestrator.enqueue_text("₹150 ki sale likh di.")
    specialist = FakeLLM()  # must stay untouched in direct mode

    result = _engine_with(orchestrator, specialist, routing="direct").run_text_turn(
        "150 ki sale likho"
    )

    assert [(t.type, t.amount_paise) for t in _transactions()] == [("sale", 15000)]
    assert result.intents == ["billing"]
    assert specialist.calls == []
    llm_events = [e for e in result.events if e.kind == "llm"]
    assert all(e.label.startswith("orchestrator") for e in llm_events)


def test_reply_sanitizer_strips_leaked_tool_markup() -> None:
    from bahi.core.orchestrator import sanitize_reply

    leaked = (
        "<tool_call>day_summary\n<arg_key>day</arg_key>\n"
        "<arg_value>null</arg_value>\n</tool_call>"
    )
    assert sanitize_reply(leaked) == ""
    mixed = "Theek hai, likh diya. <tool_call>add_sale</tool_call>"
    assert sanitize_reply(mixed) == "Theek hai, likh diya."
    assert sanitize_reply("₹200 udhaar likh diya.") == "₹200 udhaar likh diya."


def test_incomplete_agent_reports_gracefully(db: str) -> None:
    orchestrator = FakeLLM()
    for _ in range(10):  # never stops calling tools -> hits max iterations
        orchestrator.enqueue_tool_call("delegate_insights", {"instruction": "hisaab"})
    specialist = FakeLLM()
    for _ in range(10):
        specialist.enqueue_text("kuch nahi")

    result = _engine_with(orchestrator, specialist).run_text_turn("aaj ka hisaab")
    assert not result.completed
    assert result.reply  # apologetic fallback, still speakable


def test_api_turn_endpoint_returns_reply_and_trace(
    db: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from bahi.api import app as app_module

    monkeypatch.setenv("BAHI_ORCHESTRATOR_PROVIDER", "fake")
    monkeypatch.setenv("BAHI_SPECIALIST_PROVIDER", "fake")
    get_settings.cache_clear()
    app_module.get_engine.cache_clear()

    client = TestClient(app_module.create_app())
    body = client.post("/api/turn", json={"text": "namaste"}).json()

    assert body["reply"]
    assert body["routing"] == "delegated"
    assert isinstance(body["trace"], list) and body["trace"]
    assert body["usage"]["input_tokens"] >= 0
    app_module.get_engine.cache_clear()
