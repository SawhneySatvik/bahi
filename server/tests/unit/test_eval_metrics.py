from __future__ import annotations

from bahi.evals.metrics import (
    aggregate,
    canonical_writes,
    evaluate_turn,
    expected_writes,
    percentile,
)
from bahi.evals.suite import ExpectedWrite, TurnSpec


def _turn(**overrides: object) -> TurnSpec:
    base: dict[str, object] = {"utterance": "test"}
    base.update(overrides)
    return TurnSpec.model_validate(base)


def _evaluate(spec: TurnSpec, **kwargs: object) -> object:
    defaults: dict[str, object] = {
        "intents": [],
        "called_tools": [],
        "delta": [],
        "reply": "theek hai",
        "seconds": 1.0,
        "llm_seconds": 0.8,
        "input_tokens": 100,
        "output_tokens": 50,
        "cost_inr": 0.01,
    }
    defaults.update(kwargs)
    return evaluate_turn(spec, **defaults)  # type: ignore[arg-type]


def test_canonical_delta_ignores_ids_and_normalizes_names() -> None:
    got = canonical_writes([("udhaar", 20000, "  Ramesh  KUMAR ")])
    want = expected_writes(
        [ExpectedWrite(type="udhaar", amount_paise=20000, customer="ramesh kumar")]
    )
    assert got == want


def test_duplicate_write_fails_multiset_equality() -> None:
    delta = canonical_writes([("sale", 15000, None), ("sale", 15000, None)])
    expected = expected_writes([ExpectedWrite(type="sale", amount_paise=15000)])
    assert delta != expected  # double-recorded sale must NOT pass


def test_intent_scoring_exact_and_any() -> None:
    spec = _turn(gold_intent="khata")
    assert _evaluate(spec, intents=["khata"]).intents_ok
    assert not _evaluate(spec, intents=["billing"]).intents_ok

    any_spec = _turn(gold_intents_any=["khata", "insights"])
    assert _evaluate(any_spec, intents=["insights"]).intents_ok
    assert not _evaluate(any_spec, intents=[]).intents_ok

    none_ok = _turn(gold_intents_any=["khata", "none"])
    assert _evaluate(none_ok, intents=[]).intents_ok
    assert _evaluate(none_ok, intents=["khata"]).intents_ok

    chitchat = _turn()  # no gold at all -> nothing may be delegated
    assert _evaluate(chitchat, intents=[]).intents_ok
    assert not _evaluate(chitchat, intents=["billing"]).intents_ok


def test_unexpected_mutation_fails_tools_even_if_required_present() -> None:
    spec = _turn(expected_tools=["add_udhaar"])
    ok = _evaluate(spec, called_tools=["find_customer", "add_udhaar"])
    assert ok.tools_ok  # extra READ is fine
    bad = _evaluate(spec, called_tools=["add_udhaar", "add_sale"])
    assert not bad.tools_ok  # extra WRITE is not


def test_task_requires_ledger_and_nonempty_reply() -> None:
    spec = _turn(
        expected_tools=["add_sale"],
        expected_ledger_delta=[{"type": "sale", "amount_paise": 15000}],
    )
    good = _evaluate(
        spec, called_tools=["add_sale"], delta=[("sale", 15000, None)], intents=[]
    )
    assert good.ledger_ok and good.task_ok
    silent = _evaluate(
        spec, called_tools=["add_sale"], delta=[("sale", 15000, None)], reply="  "
    )
    assert silent.ledger_ok and not silent.task_ok


def test_percentile_and_aggregate_math() -> None:
    assert percentile([1, 2, 3, 4, 5], 50) == 3
    assert percentile([], 95) == 0.0
    turns = [
        _evaluate(_turn(), cost_inr=0.02),
        _evaluate(_turn(gold_intent="khata"), intents=[]),  # intent fail
    ]
    agg = aggregate(turns)  # type: ignore[arg-type]
    assert agg.turns == 2
    assert agg.intent_accuracy == 0.5
    assert agg.total_cost_inr == 0.03
    assert agg.unpriced_turns == 0
