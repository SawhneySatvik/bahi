"""Ledger tools — defined ONCE as plain typed functions.

Consumed two ways:
- in-process by the agent loop via `ledger_tool_registry()` (ToolSpec derived
  from each signature, LedgerError -> {"error": ...} so the LLM can recover)
- as a real MCP server via `bahi.mcp_server.server` (FastMCP registers the
  same functions)

Each call opens its own session: tools are the transaction boundary.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bahi.config import get_settings
from bahi.ledger.db import session_scope
from bahi.ledger.repository import LedgerError, LedgerRepository, rupees
from bahi.mcp_server.schema import schema_from_signature
from bahi.providers.base import ToolSpec

ToolResult = dict[str, Any]


def _repo(session: Any) -> LedgerRepository:
    return LedgerRepository(session, tz=get_settings().tz)


def add_sale(
    amount_paise: int,
    items: list[dict[str, Any]] | None = None,
    customer_name: str | None = None,
    note: str | None = None,
) -> ToolResult:
    """Record a sale (cash/UPI). amount_paise is the total in paise (₹1 = 100 paise).
    Optionally attach line items [{name, qty, unit_price_paise}] and a customer name."""
    with session_scope() as session:
        txn = _repo(session).add_sale(amount_paise, items, customer_name, note)
        return {
            "transaction_id": txn.id,
            "type": "sale",
            "amount_paise": txn.amount_paise,
            "amount": rupees(txn.amount_paise),
        }


def add_udhaar(
    customer_name: str,
    amount_paise: int,
    items: list[dict[str, Any]] | None = None,
    note: str | None = None,
) -> ToolResult:
    """Record udhaar (credit) given to a customer — they now owe this much more.
    Creates the customer if new. amount_paise is in paise (₹1 = 100 paise)."""
    with session_scope() as session:
        repo = _repo(session)
        txn = repo.add_udhaar(customer_name, amount_paise, items, note)
        assert txn.customer is not None
        balance = repo.balance_paise(txn.customer)
        return {
            "transaction_id": txn.id,
            "type": "udhaar",
            "customer": txn.customer.name,
            "amount_paise": txn.amount_paise,
            "amount": rupees(txn.amount_paise),
            "new_balance_paise": balance,
            "new_balance": rupees(balance),
        }


def record_repayment(customer_name: str, amount_paise: int, note: str | None = None) -> ToolResult:
    """Record a repayment from a customer against their udhaar balance.
    Fails with a speakable error if it exceeds what they owe."""
    with session_scope() as session:
        repo = _repo(session)
        txn = repo.record_repayment(customer_name, amount_paise, note)
        assert txn.customer is not None
        balance = repo.balance_paise(txn.customer)
        return {
            "transaction_id": txn.id,
            "type": "repayment",
            "customer": txn.customer.name,
            "amount_paise": txn.amount_paise,
            "amount": rupees(txn.amount_paise),
            "remaining_balance_paise": balance,
            "remaining_balance": rupees(balance),
        }


def get_balance(customer_name: str) -> ToolResult:
    """How much a customer currently owes (their udhaar balance)."""
    with session_scope() as session:
        repo = _repo(session)
        customer = repo.find_customer(customer_name)
        balance = repo.balance_paise(customer)
        return {
            "customer": customer.name,
            "balance_paise": balance,
            "balance": rupees(balance),
        }


def list_debtors() -> ToolResult:
    """All customers with outstanding udhaar, largest first."""
    with session_scope() as session:
        repo = _repo(session)
        debtors = sorted(repo.list_debtors(), key=lambda cb: -cb[1])
        return {
            "debtors": [
                {"customer": c.name, "balance_paise": b, "balance": rupees(b)}
                for c, b in debtors
            ],
            "total_outstanding_paise": sum(b for _, b in debtors),
            "total_outstanding": rupees(sum(b for _, b in debtors)),
        }


def day_summary(day: str | None = None) -> ToolResult:
    """Totals for one day (YYYY-MM-DD, default today): sales, udhaar given,
    repayments received, cash in."""
    with session_scope() as session:
        summary = _repo(session).day_summary(day)
        summary["sales"] = rupees(summary["sales_paise"])
        summary["udhaar_given"] = rupees(summary["udhaar_given_paise"])
        summary["repayments_received"] = rupees(summary["repayments_received_paise"])
        summary["cash_in"] = rupees(summary["cash_in_paise"])
        return summary


def find_customer(query: str) -> ToolResult:
    """Resolve a (possibly partial) customer name to the exact ledger customer."""
    with session_scope() as session:
        customer = _repo(session).find_customer(query)
        return {"customer": customer.name, "customer_id": customer.id}


LEDGER_TOOL_FUNCTIONS: list[Callable[..., ToolResult]] = [
    add_sale,
    add_udhaar,
    record_repayment,
    get_balance,
    list_debtors,
    day_summary,
    find_customer,
]


@dataclass(frozen=True)
class LedgerTool:
    spec: ToolSpec
    fn: Any


class ToolRegistry:
    """In-process tool surface for the agent loop. Domain errors become
    {"error": ...} results so the LLM can recover conversationally."""

    def __init__(self, tools: list[LedgerTool]) -> None:
        self._tools = {t.spec.name: t for t in tools}

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self._tools.values()]

    def subset(self, names: list[str]) -> ToolRegistry:
        return ToolRegistry([self._tools[n] for n in names])

    def call(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"Unknown tool '{name}'. Available: {sorted(self._tools)}"}
        try:
            result: ToolResult = tool.fn(**arguments)
            return result
        except LedgerError as exc:
            return {"error": str(exc)}
        except TypeError as exc:
            return {"error": f"Bad arguments for {name}: {exc}"}


def ledger_tool_registry() -> ToolRegistry:
    tools = [
        LedgerTool(
            spec=ToolSpec(
                name=fn.__name__,
                description=(fn.__doc__ or "").strip(),
                parameters=schema_from_signature(fn),
            ),
            fn=fn,
        )
        for fn in LEDGER_TOOL_FUNCTIONS
    ]
    return ToolRegistry(tools)
