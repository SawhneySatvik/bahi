"""Eval runner: executes a suite through the REAL pipeline against whatever
profile the environment selects. Fresh temp database per case; `given` state
applied before the first turn; every metric computed from ground truth.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from bahi.api.audio import to_canonical_wav
from bahi.config import get_settings
from bahi.core.orchestrator import TurnEngine, TurnResult
from bahi.core.voice import VoiceLoop
from bahi.evals import cost as cost_tables
from bahi.evals.metrics import TurnEval, Write, aggregate, canonical_writes, evaluate_turn
from bahi.evals.suite import CaseSpec, Suite, TurnSpec
from bahi.evals.wer import wer as compute_wer
from bahi.ledger.db import _engines, get_engine, init_db, session_scope
from bahi.ledger.models import Transaction
from bahi.ledger.repository import LedgerRepository

AUDIO_ROOT = Path(__file__).parents[3] / "evals" / "audio"


def _snapshot(db_url: str) -> tuple[int, list[tuple[int, str, int, str | None]]]:
    with session_scope(db_url) as session:
        rows = [
            (t.id, t.type, t.amount_paise, t.customer.name if t.customer else None)
            for t in session.scalars(select(Transaction))
        ]
    max_id = max((r[0] for r in rows), default=0)
    return max_id, rows


def _delta_after(db_url: str, prev_max_id: int) -> list[Write]:
    _, rows = _snapshot(db_url)
    return canonical_writes([(t, a, c) for i, t, a, c in rows if i > prev_max_id])


def _apply_given(case: CaseSpec, db_url: str, tz: str) -> None:
    with session_scope(db_url) as session:
        repo = LedgerRepository(session, tz=tz)
        for txn in case.given.transactions:
            if txn.type == "sale":
                repo.add_sale(txn.amount_paise, customer_name=txn.customer)
            elif txn.type == "udhaar":
                assert txn.customer, f"given udhaar needs customer (case {case.id})"
                repo.add_udhaar(txn.customer, txn.amount_paise)
            elif txn.type == "repayment":
                assert txn.customer, f"given repayment needs customer (case {case.id})"
                repo.record_repayment(txn.customer, txn.amount_paise)


def _turn_cost_inr(events: list[Any]) -> float | None:
    total, any_priced = 0.0, False
    for event in events:
        cost: float | None = None
        if event.kind == "llm":
            cost = cost_tables.llm_cost_inr(
                str(event.detail.get("model", "")),
                int(event.detail.get("input_tokens", 0)),
                int(event.detail.get("output_tokens", 0)),
            )
        elif event.kind == "stt":
            cost = cost_tables.stt_cost_inr(
                str(event.detail.get("provider", "")),
                float(event.detail.get("audio_seconds", 0.0)),
            )
        elif event.kind == "tts":
            cost = cost_tables.tts_cost_inr(
                str(event.detail.get("provider", "")),
                int(event.detail.get("characters", 0)),
                float(event.detail.get("audio_seconds", 0.0)),
            )
        else:
            continue
        if cost is None:
            return None
        total += cost
        any_priced = True
    return total if any_priced else 0.0


def _run_one_turn(
    spec: TurnSpec, engine: TurnEngine, voice: VoiceLoop | None
) -> tuple[TurnResult, float, float | None]:
    """Returns (turn_result, wall_seconds, wer_or_None)."""
    if spec.audio and voice is not None:
        raw = (AUDIO_ROOT / spec.audio).read_bytes()
        voice_result = voice.run(to_canonical_wav(raw))
        reference = spec.gold_transcript or spec.utterance
        return (
            voice_result.turn,
            voice_result.total_seconds,
            compute_wer(reference, voice_result.transcript),
        )
    return (result := engine.run_text_turn(spec.utterance)), result.seconds, None


def run_case(case: CaseSpec, sleep_s: float) -> list[TurnEval]:
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)  # noqa: SIM115
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"
    os.environ["DATABASE_URL"] = db_url
    get_settings.cache_clear()
    settings = get_settings()
    init_db(get_engine(db_url))
    _apply_given(case, db_url, settings.tz)

    engine = TurnEngine.from_settings(settings)
    voice = (
        VoiceLoop.from_settings(settings, engine=engine)
        if any(t.audio for t in case.turns)
        else None
    )
    evals: list[TurnEval] = []
    for spec in case.turns:
        prev_max_id, _ = _snapshot(db_url)
        try:
            result, wall_seconds, turn_wer = _run_one_turn(spec, engine, voice)
        except Exception as exc:  # noqa: BLE001 — one flaky call must not kill a 40-case run
            evals.append(
                evaluate_turn(
                    spec,
                    intents=[],
                    called_tools=[],
                    delta=_delta_after(db_url, prev_max_id),
                    reply="",
                    seconds=0.0,
                    llm_seconds=0.0,
                    input_tokens=0,
                    output_tokens=0,
                    cost_inr=0.0,
                )
            )
            evals[-1].detail["exception"] = repr(exc)[:300]
            print(f"    ! turn crashed: {exc!r}"[:160], flush=True)
            continue
        delta = _delta_after(db_url, prev_max_id)
        called_tools = [
            event.label.rsplit(":", 1)[1] for event in result.events if event.kind == "tool"
        ]
        errored_tools = [
            event.label.rsplit(":", 1)[1]
            for event in result.events
            if event.kind == "tool" and "error" in (event.detail.get("result") or {})
        ]
        llm_seconds = sum(e.seconds for e in result.events if e.kind == "llm")
        evals.append(
            evaluate_turn(
                spec,
                intents=result.intents,
                called_tools=called_tools,
                errored_tools=errored_tools,
                delta=delta,
                reply=result.reply,
                seconds=wall_seconds,
                llm_seconds=llm_seconds,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_inr=_turn_cost_inr(result.events),
                wer=turn_wer,
            )
        )
        if sleep_s:
            time.sleep(sleep_s)

    _engines.pop(db_url, None)
    Path(tmp.name).unlink(missing_ok=True)
    return evals


def run_suite(
    suite: Suite,
    label: str,
    repeats: int = 1,
    sleep_s: float = 0.0,
    results_dir: Path | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    runs: list[dict[str, Any]] = []
    for repeat in range(repeats):
        all_evals: list[TurnEval] = []
        case_records: list[dict[str, Any]] = []
        for case in suite.cases:
            evals = run_case(case, sleep_s)
            all_evals.extend(evals)
            case_records.append(
                {
                    "id": case.id,
                    "tags": case.tags,
                    "lang": case.lang,
                    "turns": [
                        {
                            "utterance": e.utterance,
                            "intents_ok": e.intents_ok,
                            "tools_ok": e.tools_ok,
                            "ledger_ok": e.ledger_ok,
                            "task_ok": e.task_ok,
                            "seconds": round(e.seconds, 3),
                            "cost_inr": e.cost_inr,
                            "wer": e.wer,
                            "detail": e.detail,
                        }
                        for e in evals
                    ],
                }
            )
            passed = sum(e.task_ok for e in evals)
            print(f"  [{passed}/{len(evals)}] {case.id}", flush=True)
        runs.append(
            {"repeat": repeat, "aggregates": aggregate(all_evals).to_dict(), "cases": case_records}
        )

    payload = {
        "label": label,
        "suite": suite.suite,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "profile": get_settings().profile_summary(),
        "routing": settings.routing,
        "repeats": repeats,
        "fx_inr_per_usd": cost_tables.FX_INR_PER_USD,
        "prices_dated": cost_tables.PRICES_DATED,
        "runs": runs,
    }
    if results_dir:
        results_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = results_dir / f"{label}_{suite.suite}_{stamp}.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"results -> {out}")
    return payload
