from __future__ import annotations

from bahi.providers.base import Message, ToolSpec
from bahi.providers.fake.llm import FakeLLM

TOOL = ToolSpec(name="add_sale", description="Record a sale", parameters={"type": "object"})


def test_scripted_queue_pops_in_order() -> None:
    llm = FakeLLM()
    llm.enqueue_tool_call("add_sale", {"amount_paise": 20000})
    llm.enqueue_text("Done, 200 rupaye ki sale likh di.")

    first = llm.complete([Message(role="user", content="200 ki sale")], [TOOL], model="fake")
    assert first.tool_calls[0].name == "add_sale"
    assert first.tool_calls[0].arguments == {"amount_paise": 20000}

    second = llm.complete([Message(role="user", content="200 ki sale")], [TOOL], model="fake")
    assert second.content == "Done, 200 rupaye ki sale likh di."
    assert second.tool_calls == ()


def test_empty_queue_echoes_last_user_message() -> None:
    llm = FakeLLM()
    turn = llm.complete(
        [
            Message(role="system", content="You are Bahi."),
            Message(role="user", content="aaj ka hisaab"),
        ],
        [],
        model="fake-orchestrator",
    )
    assert turn.content is not None
    assert "aaj ka hisaab" in turn.content


def test_calls_are_recorded_for_assertions() -> None:
    llm = FakeLLM()
    llm.complete([Message(role="user", content="hi")], [TOOL], model="m1", temperature=0.0)
    assert llm.calls[0]["tools"] == ["add_sale"]
    assert llm.calls[0]["model"] == "m1"
