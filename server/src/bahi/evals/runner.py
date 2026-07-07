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

from bahi.config import get_settings
from bahi.core.orchestrator import TurnEngine
from bahi.evals import cost as cost_tables
from bahi.evals.metrics import TurnEval, Write, aggregate, canonical_writes, evaluate_turn
from bahi.evals.suite import CaseSpec, Suite
from bahi.ledger.db import _engines, get_engine, init_db, session_scope
from bahi.ledger.models import Transaction
from bahi.ledger.repository import LedgerRepository


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
        if event.kind != "llm":
            continue
        cost = cost_tables.llm_cost_inr(
            str(event.detail.get("model", "")),
            int(event.detail.get("input_tokens", 0)),
            int(event.detail.get("output_tokens", 0)),
        )
        if cost is None:
            return None
        total += cost
        any_priced = True
    return total if any_priced else 0.0


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
    evals: list[TurnEval] = []
    for spec in case.turns:
        prev_max_id, _ = _snapshot(db_url)
        result = engine.run_text_turn(spec.utterance)
        delta = _delta_after(db_url, prev_max_id)
        called_tools = [
            event.label.rsplit(":", 1)[1] for event in result.events if event.kind == "tool"
        ]
        llm_seconds = sum(e.seconds for e in result.events if e.kind == "llm")
        evals.append(
            evaluate_turn(
                spec,
                intents=result.intents,
                called_tools=called_tools,
                delta=delta,
                reply=result.reply,
                seconds=result.seconds,
                llm_seconds=llm_seconds,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cost_inr=_turn_cost_inr(result.events),
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
