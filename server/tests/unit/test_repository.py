from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from bahi.ledger.models import Base, Transaction
from bahi.ledger.repository import (
    AmbiguousCustomerError,
    CustomerNotFoundError,
    InvalidAmountError,
    LedgerRepository,
    RepaymentExceedsBalanceError,
    normalize_name,
    rupees,
)

DB_URLS = ["sqlite://"]
if os.environ.get("TEST_POSTGRES_URL"):
    DB_URLS.append(os.environ["TEST_POSTGRES_URL"])


@pytest.fixture(params=DB_URLS)
def session(request: pytest.FixtureRequest) -> Iterator[Session]:
    engine = create_engine(request.param)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as s:
        yield s
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def repo(session: Session) -> LedgerRepository:
    return LedgerRepository(session, tz="Asia/Kolkata")


def test_udhaar_creates_customer_and_balance(repo: LedgerRepository) -> None:
    txn = repo.add_udhaar("Ramesh", 20000)
    assert txn.customer is not None and txn.customer.name == "Ramesh"
    assert repo.balance_paise(txn.customer) == 20000


def test_repayment_reduces_balance(repo: LedgerRepository) -> None:
    repo.add_udhaar("Ramesh", 20000)
    repo.record_repayment("Ramesh", 5000)
    customer = repo.find_customer("Ramesh")
    assert repo.balance_paise(customer) == 15000


def test_repayment_exceeding_balance_raises(repo: LedgerRepository) -> None:
    repo.add_udhaar("Ramesh", 10000)
    with pytest.raises(RepaymentExceedsBalanceError) as exc:
        repo.record_repayment("Ramesh", 20000)
    assert exc.value.balance_paise == 10000


def test_repayment_for_unknown_customer_raises(repo: LedgerRepository) -> None:
    with pytest.raises(CustomerNotFoundError):
        repo.record_repayment("Ghost", 100)


def test_amount_must_be_positive_int(repo: LedgerRepository) -> None:
    for bad in (0, -5):
        with pytest.raises(InvalidAmountError):
            repo.add_sale(bad)


def test_find_customer_exact_beats_substring(repo: LedgerRepository) -> None:
    repo.add_udhaar("Ram", 100)
    repo.add_udhaar("Ramesh", 100)
    assert repo.find_customer("ram").name == "Ram"  # exact normalized match wins
    assert repo.find_customer("RAMESH").name == "Ramesh"


def test_find_customer_unique_substring(repo: LedgerRepository) -> None:
    repo.add_udhaar("Ramesh Kumar", 100)
    repo.add_udhaar("Suresh", 100)
    assert repo.find_customer("kumar").name == "Ramesh Kumar"


def test_find_customer_ambiguous_lists_candidates(repo: LedgerRepository) -> None:
    repo.add_udhaar("Ramesh", 100)
    repo.add_udhaar("Rameshwar", 100)
    with pytest.raises(AmbiguousCustomerError) as exc:
        repo.find_customer("ramesh"[:5])  # "rames" matches both
    assert set(exc.value.candidates) == {"Ramesh", "Rameshwar"}


def test_customer_dedup_is_case_and_space_insensitive(repo: LedgerRepository) -> None:
    a = repo.get_or_create_customer("Ramesh  Kumar")
    b = repo.get_or_create_customer(" ramesh kumar ")
    assert a.id == b.id
    assert normalize_name("  Ramesh   KUMAR ") == "ramesh kumar"


def test_anonymous_sale(repo: LedgerRepository) -> None:
    txn = repo.add_sale(5000, items=[{"name": "Parle-G", "qty": 2, "unit_price_paise": 2500}])
    assert txn.customer_id is None
    assert txn.items is not None and txn.items[0]["name"] == "Parle-G"


def test_day_summary_totals_and_counts(repo: LedgerRepository, session: Session) -> None:
    repo.add_sale(10000)
    repo.add_udhaar("Ramesh", 20000)
    repo.record_repayment("Ramesh", 5000)
    today = datetime.now(repo._tz).strftime("%Y-%m-%d")  # noqa: SLF001
    summary = repo.day_summary(today)
    assert summary["sales_paise"] == 10000
    assert summary["udhaar_given_paise"] == 20000
    assert summary["repayments_received_paise"] == 5000
    assert summary["cash_in_paise"] == 15000
    assert summary["counts"] == {"sale": 1, "udhaar": 1, "repayment": 1}


def test_day_summary_ist_boundary(repo: LedgerRepository, session: Session) -> None:
    # 2026-07-07 20:00 UTC == 2026-07-08 01:30 IST -> belongs to the 8th, not the 7th
    txn = repo.add_sale(7700)
    session.get(Transaction, txn.id)
    txn.ts = datetime(2026, 7, 7, 20, 0, 0)
    session.flush()
    assert repo.day_summary("2026-07-08")["sales_paise"] == 7700
    assert repo.day_summary("2026-07-07")["sales_paise"] == 0


def test_list_debtors_excludes_settled(repo: LedgerRepository) -> None:
    repo.add_udhaar("Ramesh", 20000)
    repo.add_udhaar("Suresh", 5000)
    repo.record_repayment("Suresh", 5000)
    debtors = repo.list_debtors()
    assert [(c.name, b) for c, b in debtors] == [("Ramesh", 20000)]


def test_rupees_formatting() -> None:
    assert rupees(20000) == "₹200.00"
    assert rupees(50) == "₹0.50"
    assert rupees(-1234) == "-₹12.34"
