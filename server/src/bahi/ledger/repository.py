"""Typed ledger operations — the single behavior source for both the
in-process agent tools and the standalone MCP server.

Errors are domain errors (LedgerError subclasses) with speakable messages;
the tool layer converts them to {"error": ...} so the LLM can recover
conversationally instead of crashing the turn.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from bahi.ledger.models import Customer, Transaction, utcnow


class LedgerError(Exception):
    """Base for domain errors; message is safe to speak back to the user."""


class InvalidAmountError(LedgerError):
    def __init__(self, amount_paise: int) -> None:
        super().__init__(f"Amount must be a positive number of paise, got {amount_paise}.")


class CustomerNotFoundError(LedgerError):
    def __init__(self, query: str, suggestions: list[str]) -> None:
        hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
        super().__init__(f"No customer matching '{query}'.{hint}")
        self.suggestions = suggestions


class AmbiguousCustomerError(LedgerError):
    def __init__(self, query: str, candidates: list[str]) -> None:
        super().__init__(
            f"'{query}' matches multiple customers: {', '.join(candidates)}. "
            "Ask the user which one they mean."
        )
        self.candidates = candidates


class RepaymentExceedsBalanceError(LedgerError):
    def __init__(self, amount_paise: int, balance_paise: int) -> None:
        super().__init__(
            f"Repayment of {rupees(amount_paise)} exceeds outstanding balance "
            f"of {rupees(balance_paise)}."
        )
        self.balance_paise = balance_paise


def normalize_name(name: str) -> str:
    return " ".join(name.casefold().split())


def rupees(paise: int) -> str:
    sign = "-" if paise < 0 else ""
    whole, frac = divmod(abs(paise), 100)
    return f"{sign}₹{whole}.{frac:02d}"


def _check_amount(amount_paise: int) -> None:
    if not isinstance(amount_paise, int) or amount_paise <= 0:
        raise InvalidAmountError(amount_paise)


class LedgerRepository:
    def __init__(self, session: Session, tz: str = "Asia/Kolkata") -> None:
        self._s = session
        self._tz = ZoneInfo(tz)

    # --- customers ---

    def get_or_create_customer(self, name: str) -> Customer:
        norm = normalize_name(name)
        if not norm:
            raise LedgerError("Customer name cannot be empty.")
        existing = self._s.scalar(select(Customer).where(Customer.name_normalized == norm))
        if existing:
            return existing
        customer = Customer(name=name.strip(), name_normalized=norm)
        self._s.add(customer)
        self._s.flush()
        return customer

    def find_customer(self, query: str) -> Customer:
        """Deterministic resolution: exact normalized match wins; otherwise a
        unique substring match; otherwise a typed domain error."""
        norm = normalize_name(query)
        exact = self._s.scalar(select(Customer).where(Customer.name_normalized == norm))
        if exact:
            return exact
        candidates = list(
            self._s.scalars(
                select(Customer)
                .where(Customer.name_normalized.like(f"%{norm}%"))
                .order_by(Customer.name_normalized)
            )
        )
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            some = list(self._s.scalars(select(Customer.name).limit(5)))
            raise CustomerNotFoundError(query, suggestions=some)
        raise AmbiguousCustomerError(query, [c.name for c in candidates])

    def balance_paise(self, customer: Customer) -> int:
        """Outstanding udhaar minus repayments (positive = customer owes)."""
        total = self._s.scalar(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (Transaction.type == "udhaar", Transaction.amount_paise),
                            else_=-Transaction.amount_paise,
                        )
                    ),
                    0,
                )
            ).where(
                Transaction.customer_id == customer.id,
                Transaction.type.in_(["udhaar", "repayment"]),
            )
        )
        return int(total or 0)

    # --- transactions ---

    def add_sale(
        self,
        amount_paise: int,
        items: list[dict[str, Any]] | None = None,
        customer_name: str | None = None,
        note: str | None = None,
    ) -> Transaction:
        _check_amount(amount_paise)
        customer = self.get_or_create_customer(customer_name) if customer_name else None
        txn = Transaction(
            type="sale",
            amount_paise=amount_paise,
            items=items,
            note=note,
            customer_id=customer.id if customer else None,
        )
        self._s.add(txn)
        self._s.flush()
        return txn

    def add_udhaar(
        self,
        customer_name: str,
        amount_paise: int,
        items: list[dict[str, Any]] | None = None,
        note: str | None = None,
    ) -> Transaction:
        _check_amount(amount_paise)
        customer = self.get_or_create_customer(customer_name)
        txn = Transaction(
            type="udhaar",
            amount_paise=amount_paise,
            items=items,
            note=note,
            customer_id=customer.id,
        )
        self._s.add(txn)
        self._s.flush()
        return txn

    def record_repayment(
        self, customer_name: str, amount_paise: int, note: str | None = None
    ) -> Transaction:
        _check_amount(amount_paise)
        customer = self.find_customer(customer_name)
        balance = self.balance_paise(customer)
        if amount_paise > balance:
            raise RepaymentExceedsBalanceError(amount_paise, balance)
        txn = Transaction(
            type="repayment",
            amount_paise=amount_paise,
            note=note,
            customer_id=customer.id,
        )
        self._s.add(txn)
        self._s.flush()
        return txn

    # --- queries ---

    def list_debtors(self) -> list[tuple[Customer, int]]:
        customers = list(self._s.scalars(select(Customer).order_by(Customer.name)))
        result = [(c, self.balance_paise(c)) for c in customers]
        return [(c, b) for c, b in result if b > 0]

    def day_summary(self, day: str | None = None) -> dict[str, Any]:
        """Totals for one shop-local calendar day (day: YYYY-MM-DD, default today)."""
        local_date = (
            datetime.strptime(day, "%Y-%m-%d").date()
            if day
            else datetime.now(self._tz).date()
        )
        start_local = datetime.combine(local_date, datetime.min.time(), tzinfo=self._tz)
        start_utc = start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        end_utc = start_utc + timedelta(days=1)

        txns = list(
            self._s.scalars(
                select(Transaction).where(Transaction.ts >= start_utc, Transaction.ts < end_utc)
            )
        )
        by_type = {"sale": 0, "udhaar": 0, "repayment": 0}
        counts = {"sale": 0, "udhaar": 0, "repayment": 0}
        for t in txns:
            by_type[t.type] += t.amount_paise
            counts[t.type] += 1
        return {
            "date": local_date.isoformat(),
            "sales_paise": by_type["sale"],
            "udhaar_given_paise": by_type["udhaar"],
            "repayments_received_paise": by_type["repayment"],
            "cash_in_paise": by_type["sale"] + by_type["repayment"],
            "counts": counts,
        }


# ts helper re-exported for tests that need to backdate transactions
__all__ = [
    "AmbiguousCustomerError",
    "CustomerNotFoundError",
    "InvalidAmountError",
    "LedgerError",
    "LedgerRepository",
    "RepaymentExceedsBalanceError",
    "normalize_name",
    "rupees",
    "utcnow",
]
