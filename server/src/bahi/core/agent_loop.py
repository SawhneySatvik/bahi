"""Provider-blind tool-calling loop.

Works with anything satisfying LLMProvider and a ToolSurface (the in-process
ledger registry, or the orchestrator's delegate board). Tool errors come back
as {"error": ...} tool results, so the model can recover conversationally.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from bahi.providers.base import LLMProvider, Message, ToolSpec

MAX_ITERATIONS = 6


class ToolSurface(Protocol):
    def specs(self) -> list[ToolSpec]: ...

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class TraceEvent:
    kind: str  # "llm" | "tool" | "delegate"
    label: str
    seconds: float
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "seconds": round(self.seconds, 3),
            **self.detail,
        }


@dataclass
class AgentResult:
    text: str
    events: list[TraceEvent]
    input_tokens: int
    output_tokens: int
    completed: bool


def run_agent(
    llm: LLMProvider,
    model: str,
    messages: list[Message],
    tools: ToolSurface,
    label: str,
    max_iterations: int = MAX_ITERATIONS,
    temperature: float = 0.0,
) -> AgentResult:
    transcript = list(messages)
    events: list[TraceEvent] = []
    input_tokens = 0
    output_tokens = 0

    for iteration in range(max_iterations):
        start = time.perf_counter()
        turn = llm.complete(transcript, tools.specs(), model=model, temperature=temperature)
        elapsed = time.perf_counter() - start
        input_tokens += turn.usage.input_tokens
        output_tokens += turn.usage.output_tokens
        events.append(
            TraceEvent(
                kind="llm",
                label=f"{label}:llm#{iteration + 1}",
                seconds=elapsed,
                detail={
                    "model": turn.model,
                    "input_tokens": turn.usage.input_tokens,
                    "output_tokens": turn.usage.output_tokens,
                },
            )
        )

        if not turn.tool_calls:
            return AgentResult(
                text=turn.content or "",
                events=events,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                completed=True,
            )

        transcript.append(turn.message)
        for tool_call in turn.tool_calls:
            tool_start = time.perf_counter()
            result = tools.call(tool_call.name, tool_call.arguments)
            tool_elapsed = time.perf_counter() - tool_start
            events.append(
                TraceEvent(
                    kind="tool",
                    label=f"{label}:{tool_call.name}",
                    seconds=tool_elapsed,
                    detail={"arguments": tool_call.arguments, "result": result},
                )
            )
            transcript.append(
                Message(
                    role="tool",
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=tool_call.id,
                    name=tool_call.name,
                )
            )

    return AgentResult(
        text="Maaf kijiye, yeh request abhi poori nahi ho paayi.",
        events=events,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        completed=False,
    )
