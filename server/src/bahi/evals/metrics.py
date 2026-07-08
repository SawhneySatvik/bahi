"""Metric definitions — the single source of truth for what 'correct' means.
Smoke tests and the eval runner share these comparators.

Canonical ledger-delta equality (docs/metrics.md): a write is the tuple
(type, amount_paise, normalized_customer_name_or_None); ids and timestamps are
ignored; comparison is MULTISET equality (a duplicate write is a failure).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bahi.evals.suite import MUTATING_TOOLS, ExpectedWrite, TurnSpec
from bahi.ledger.repository import normalize_name

Write = tuple[str, int, str | None]


def canonical_writes(rows: list[tuple[str, int, str | None]]) -> list[Write]:
    """rows: (type, amount_paise, customer_name_or_None) -> sorted multiset."""
    return sorted(
        (t, amount, normalize_name(name) if name else None) for t, amount, name in rows
    )


def expected_writes(spec: list[ExpectedWrite]) -> list[Write]:
    return sorted(
        (w.type, w.amount_paise, normalize_name(w.customer) if w.customer else None)
        for w in spec
    )


@dataclass
class TurnEval:
    utterance: str
    intents_ok: bool
    tools_ok: bool
    ledger_ok: bool
    task_ok: bool
    seconds: float
    llm_seconds: float
    input_tokens: int
    output_tokens: int
    cost_inr: float | None
    wer: float | None = None  # audio turns only
    detail: dict[str, Any] = field(default_factory=dict)


def evaluate_turn(
    spec: TurnSpec,
    intents: list[str],
    called_tools: list[str],
    delta: list[Write],
    reply: str,
    seconds: float,
    llm_seconds: float,
    input_tokens: int,
    output_tokens: int,
    cost_inr: float | None,
    errored_tools: list[str] | None = None,
    wer: float | None = None,
) -> TurnEval:
    gold = set(spec.gold_intents)
    if spec.gold_intents_any:
        accepted = set(spec.gold_intents_any)
        intents_ok = bool(accepted & set(intents)) or ("none" in accepted and not intents)
        if gold:  # required intents still apply on top of the any-of set
            intents_ok = intents_ok and gold <= set(intents)
    else:
        intents_ok = gold <= set(intents) if gold else not intents

    called = set(called_tools)
    required_ok = set(spec.expected_tools) <= called
    # An attempted mutation the ledger REFUSED (error result, no write) is
    # legitimate discovery ("Ghost ne 100 wapas kiye" -> record_repayment ->
    # 'no such customer'), not an unexpected mutation. Actual writes are
    # already policed by canonical delta equality.
    unexpected_mutations = (
        (called & MUTATING_TOOLS) - set(spec.expected_tools) - set(errored_tools or [])
    )
    tools_ok = required_ok and not unexpected_mutations

    ledger_ok = delta == expected_writes(spec.expected_ledger_delta)
    task_ok = ledger_ok and bool(reply.strip())

    return TurnEval(
        utterance=spec.utterance,
        intents_ok=intents_ok,
        tools_ok=tools_ok,
        ledger_ok=ledger_ok,
        task_ok=task_ok,
        seconds=seconds,
        llm_seconds=llm_seconds,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_inr=cost_inr,
        wer=wer,
        detail={
            "intents": intents,
            "gold_intents": sorted(gold),
            "called_tools": sorted(called),
            "expected_tools": spec.expected_tools,
            "unexpected_mutations": sorted(unexpected_mutations),
            "delta": delta,
            "expected_delta": expected_writes(spec.expected_ledger_delta),
            "reply": reply,
        },
    )


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int(round((pct / 100) * (len(ordered) - 1))), len(ordered) - 1)
    return ordered[index]


@dataclass
class Aggregates:
    turns: int
    intent_accuracy: float
    tool_correctness: float
    ledger_match: float
    task_success: float
    latency_p50: float
    latency_p95: float
    llm_seconds_p50: float
    total_cost_inr: float
    unpriced_turns: int
    cost_per_turn_inr: float
    input_tokens: int
    output_tokens: int
    audio_turns: int = 0
    wer_mean: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def aggregate(turn_evals: list[TurnEval]) -> Aggregates:
    n = len(turn_evals) or 1
    seconds = [t.seconds for t in turn_evals]
    priced = [t.cost_inr for t in turn_evals if t.cost_inr is not None]
    total_cost = sum(priced)
    wers = [t.wer for t in turn_evals if t.wer is not None]
    return Aggregates(
        audio_turns=len(wers),
        wer_mean=round(sum(wers) / len(wers), 4) if wers else None,
        turns=len(turn_evals),
        intent_accuracy=sum(t.intents_ok for t in turn_evals) / n,
        tool_correctness=sum(t.tools_ok for t in turn_evals) / n,
        ledger_match=sum(t.ledger_ok for t in turn_evals) / n,
        task_success=sum(t.task_ok for t in turn_evals) / n,
        latency_p50=percentile(seconds, 50),
        latency_p95=percentile(seconds, 95),
        llm_seconds_p50=percentile([t.llm_seconds for t in turn_evals], 50),
        total_cost_inr=round(total_cost, 4),
        unpriced_turns=sum(t.cost_inr is None for t in turn_evals),
        cost_per_turn_inr=round(total_cost / (len(priced) or 1), 4),
        input_tokens=sum(t.input_tokens for t in turn_evals),
        output_tokens=sum(t.output_tokens for t in turn_evals),
    )
