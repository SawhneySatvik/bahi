"""TurnEngine: one shopkeeper utterance in, one spoken-style reply + trace out.

Two routing strategies (env: BAHI_ROUTING):
- delegated — orchestrator LLM routes via delegate_* tools; each delegation runs
  a specialist agent-loop over its scoped ledger tools; orchestrator synthesizes.
- direct — orchestrator LLM holds all ledger tools itself (one hop, lower
  latency; the A/B table reports the trade-off).

Everything here holds Protocols only — no vendor can appear in this module.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from bahi.config import Settings
from bahi.core import prompts
from bahi.core.agent_loop import AgentResult, TraceEvent, run_agent
from bahi.mcp_server.tools import ToolRegistry, ledger_tool_registry
from bahi.providers.base import LLMProvider, Message, ToolSpec
from bahi.providers.factory import build_llm

# Some models occasionally leak textual tool-call markup into their final text
# (observed live on sarvam-105b). Anything like this must never be spoken.
_MARKUP = re.compile(r"<[/]?(tool_call|arg_key|arg_value)[^>]*>.*?(?=<|$)", re.DOTALL)


def sanitize_reply(text: str) -> str:
    return _MARKUP.sub("", text).strip()


SPECIALISTS: dict[str, dict[str, Any]] = {
    "khata": {
        "description": (
            "Udhaar / credit ledger: record udhaar given, record repayments, "
            "check balances, list debtors."
        ),
        "tools": ["add_udhaar", "record_repayment", "get_balance", "list_debtors", "find_customer"],
    },
    "billing": {
        "description": "Sales: record a sale (cash/UPI), optionally with line items.",
        "tools": ["add_sale", "find_customer"],
    },
    "insights": {
        "description": (
            "Business questions: today's/any day's summary (sales, udhaar, repayments, "
            "cash in), who owes what."
        ),
        "tools": ["day_summary", "list_debtors", "get_balance"],
    },
}


class DelegateBoard:
    """The orchestrator's tool surface in delegated mode: one delegate_<name>
    tool per specialist; calling it runs that specialist's agent loop."""

    def __init__(
        self,
        specialist_llm: LLMProvider,
        specialist_model: str,
        registry: ToolRegistry,
        utterance: str,
        prompt_suffix: str = "",
    ) -> None:
        self._llm = specialist_llm
        self._model = specialist_model
        self._registry = registry
        self._utterance = utterance
        self._prompt_suffix = prompt_suffix
        self.events: list[TraceEvent] = []
        self.delegations: list[str] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self._completed: dict[tuple[str, str], str] = {}

    def specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=f"delegate_{name}",
                description=str(config["description"])
                + " Pass a complete instruction including names, amounts, and items.",
                parameters={
                    "type": "object",
                    "properties": {"instruction": {"type": "string"}},
                    "required": ["instruction"],
                },
            )
            for name, config in SPECIALISTS.items()
        ]

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        specialist = name.removeprefix("delegate_")
        if specialist not in SPECIALISTS:
            return {"error": f"Unknown specialist '{specialist}'."}
        instruction = str(arguments.get("instruction", ""))
        # Ledger safety: an identical repeat delegation replays the previous
        # reply instead of re-running (guards against orchestrator loops
        # double-writing transactions or spiraling into "verification" hops).
        key = (specialist, " ".join(instruction.lower().split()))
        if key in self._completed:
            return {
                "specialist": specialist,
                "reply": self._completed[key],
                "note": "Already done earlier this turn — do NOT delegate again; "
                "give your final spoken reply now.",
            }
        self.delegations.append(specialist)

        start = time.perf_counter()
        result = run_agent(
            llm=self._llm,
            model=self._model,
            messages=[
                Message(
                    role="system",
                    content=prompts.SPECIALIST_PROMPTS[specialist] + self._prompt_suffix,
                ),
                Message(
                    role="user",
                    content=(
                        f"Shopkeeper said: \"{self._utterance}\"\n"
                        f"Your task: {instruction}"
                    ),
                ),
            ],
            tools=self._registry.subset(list(SPECIALISTS[specialist]["tools"])),
            label=f"specialist:{specialist}",
        )
        elapsed = time.perf_counter() - start
        self.events.extend(result.events)
        self.events.append(
            TraceEvent(
                kind="delegate",
                label=f"delegate:{specialist}",
                seconds=elapsed,
                detail={"instruction": instruction, "reply": result.text},
            )
        )
        self.input_tokens += result.input_tokens
        self.output_tokens += result.output_tokens
        self._completed[key] = result.text
        return {"specialist": specialist, "reply": result.text}


@dataclass
class TurnResult:
    reply: str
    routing: str
    intents: list[str]
    events: list[TraceEvent]
    input_tokens: int
    output_tokens: int
    seconds: float
    completed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "routing": self.routing,
            "intents": self.intents,
            "seconds": round(self.seconds, 3),
            "usage": {"input_tokens": self.input_tokens, "output_tokens": self.output_tokens},
            "completed": self.completed,
            "trace": [e.to_dict() for e in self.events],
        }


class TurnEngine:
    def __init__(
        self,
        orchestrator_llm: LLMProvider,
        orchestrator_model: str,
        specialist_llm: LLMProvider,
        specialist_model: str,
        registry: ToolRegistry,
        routing: str = "delegated",
        tz: str = "Asia/Kolkata",
    ) -> None:
        self._orchestrator_llm = orchestrator_llm
        self._orchestrator_model = orchestrator_model
        self._specialist_llm = specialist_llm
        self._specialist_model = specialist_model
        self._registry = registry
        self._routing = routing
        self._tz = tz

    @classmethod
    def from_settings(cls, settings: Settings) -> TurnEngine:
        orchestrator_llm, orchestrator_model = build_llm(settings, "orchestrator")
        specialist_llm, specialist_model = build_llm(settings, "specialist")
        return cls(
            orchestrator_llm=orchestrator_llm,
            orchestrator_model=orchestrator_model,
            specialist_llm=specialist_llm,
            specialist_model=specialist_model,
            registry=ledger_tool_registry(),
            routing=settings.routing,
            tz=settings.tz,
        )

    def run_text_turn(self, text: str) -> TurnResult:
        start = time.perf_counter()
        date_suffix = prompts.today_line(self._tz)
        if self._routing == "direct":
            result = run_agent(
                llm=self._orchestrator_llm,
                model=self._orchestrator_model,
                messages=[
                    Message(role="system", content=prompts.ORCHESTRATOR_DIRECT + date_suffix),
                    Message(role="user", content=text),
                ],
                tools=self._registry,
                label="orchestrator",
            )
            intents = sorted(
                {
                    specialist
                    for event in result.events
                    if event.kind == "tool"
                    for specialist, config in SPECIALISTS.items()
                    if event.label.split(":", 1)[1] in config["tools"]
                }
            )
            return self._finish(result, intents, start)

        board = DelegateBoard(
            self._specialist_llm,
            self._specialist_model,
            self._registry,
            utterance=text,
            prompt_suffix=date_suffix,
        )
        result = run_agent(
            llm=self._orchestrator_llm,
            model=self._orchestrator_model,
            messages=[
                Message(role="system", content=prompts.ORCHESTRATOR_DELEGATED + date_suffix),
                Message(role="user", content=text),
            ],
            tools=board,
            label="orchestrator",
        )
        # Some models return empty text after tool results (observed live on
        # gemini-2.5-flash-lite) — fall back to the last specialist reply so
        # the turn is never silent.
        reply_text = sanitize_reply(result.text)
        if not reply_text:
            delegate_replies = [
                sanitize_reply(str(e.detail.get("reply", "")))
                for e in board.events
                if e.kind == "delegate"
            ]
            reply_text = next((r for r in reversed(delegate_replies) if r), "")
        merged = AgentResult(
            text=reply_text,
            events=[*result.events, *board.events],
            input_tokens=result.input_tokens + board.input_tokens,
            output_tokens=result.output_tokens + board.output_tokens,
            completed=result.completed,
        )
        return self._finish(merged, board.delegations, start)

    def _finish(self, result: AgentResult, intents: list[str], start: float) -> TurnResult:
        return TurnResult(
            reply=sanitize_reply(result.text),
            routing=self._routing,
            intents=intents,
            events=result.events,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            seconds=time.perf_counter() - start,
            completed=result.completed,
        )
