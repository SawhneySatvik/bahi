"""The in-process tool surface: schemas from signatures, speakable errors."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from bahi.config import get_settings
from bahi.ledger.db import _engines, get_engine, init_db
from bahi.mcp_server.tools import ledger_tool_registry


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    db_url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("DATABASE_URL", db_url)
    get_settings.cache_clear()
    init_db(get_engine(db_url))
    yield ledger_tool_registry()
    get_settings.cache_clear()
    _engines.clear()


def test_all_seven_tools_have_specs(registry) -> None:  # type: ignore[no-untyped-def]
    names = {spec.name for spec in registry.specs()}
    assert names == {
        "add_sale",
        "add_udhaar",
        "record_repayment",
        "get_balance",
        "list_debtors",
        "day_summary",
        "find_customer",
    }
    for spec in registry.specs():
        assert spec.description, f"{spec.name} needs a description for the LLM"


def test_schema_marks_required_vs_optional(registry) -> None:  # type: ignore[no-untyped-def]
    spec = next(s for s in registry.specs() if s.name == "add_udhaar")
    assert spec.parameters["required"] == ["customer_name", "amount_paise"]
    assert spec.parameters["properties"]["amount_paise"] == {"type": "integer"}
    assert spec.parameters["properties"]["items"]["type"] == "array"


def test_udhaar_then_balance_roundtrip(registry) -> None:  # type: ignore[no-untyped-def]
    result = registry.call("add_udhaar", {"customer_name": "Ramesh", "amount_paise": 20000})
    assert result["new_balance_paise"] == 20000
    assert result["new_balance"] == "₹200.00"
    balance = registry.call("get_balance", {"customer_name": "ramesh"})
    assert balance["balance_paise"] == 20000


def test_domain_error_becomes_speakable_result(registry) -> None:  # type: ignore[no-untyped-def]
    registry.call("add_udhaar", {"customer_name": "Ramesh", "amount_paise": 100})
    result = registry.call(
        "record_repayment", {"customer_name": "Ramesh", "amount_paise": 99999}
    )
    assert "error" in result and "exceeds" in result["error"]


def test_unknown_tool_and_bad_args_are_recoverable(registry) -> None:  # type: ignore[no-untyped-def]
    assert "error" in registry.call("no_such_tool", {})
    assert "error" in registry.call("get_balance", {"nope": 1})


def test_subset_scopes_specialist_tools(registry) -> None:  # type: ignore[no-untyped-def]
    khata = registry.subset(["add_udhaar", "record_repayment", "get_balance", "list_debtors"])
    assert len(khata.specs()) == 4
    assert "error" in khata.call("add_sale", {"amount_paise": 100})
