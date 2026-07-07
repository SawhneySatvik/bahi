"""Deterministic scripted LLM for offline tests.

Tests enqueue AssistantTurns (or shorthand dicts); each `complete` call pops
the next one, so multi-hop orchestrator → specialist → synthesis flows are
fully scriptable. With an empty queue it echoes the last user message, which
is enough for smoke paths that only need *a* response.
"""

from __future__ import annotations

from collections import deque
from typing import Any

from bahi.providers.base import AssistantTurn, LLMUsage, Message, ToolCall, ToolSpec


class FakeLLM:
    name = "fake"

    def __init__(self, **_: Any) -> None:
        self._queue: deque[AssistantTurn] = deque()
        self.calls: list[dict[str, Any]] = []

    # --- scripting API (used by tests) ---

    def enqueue_text(self, content: str) -> None:
        self._queue.append(
            AssistantTurn(content=content, tool_calls=(), usage=LLMUsage(), model="fake")
        )

    def enqueue_tool_call(
        self, name: str, arguments: dict[str, Any], call_id: str | None = None
    ) -> None:
        call = ToolCall(
            id=call_id or f"call_{len(self.calls)}_{name}", name=name, arguments=arguments
        )
        self._queue.append(
            AssistantTurn(content=None, tool_calls=(call,), usage=LLMUsage(), model="fake")
        )

    def enqueue(self, turn: AssistantTurn) -> None:
        self._queue.append(turn)

    # --- LLMProvider contract ---

    def complete(
        self,
        messages: list[Message],
        tools: list[ToolSpec],
        model: str,
        temperature: float = 0.0,
    ) -> AssistantTurn:
        self.calls.append(
            {
                "messages": list(messages),
                "tools": [t.name for t in tools],
                "model": model,
                "temperature": temperature,
            }
        )
        if self._queue:
            return self._queue.popleft()
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return AssistantTurn(
            content=f"[fake:{model}] {last_user or 'ok'}",
            tool_calls=(),
            usage=LLMUsage(input_tokens=len(messages), output_tokens=1),
            model=model,
        )
