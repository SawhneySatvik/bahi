from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bahi.api.app import create_app
from bahi.config import get_settings
from bahi.ledger.db import get_engine, init_db, session_scope
from bahi.ledger.repository import LedgerRepository


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    url = f"sqlite:///{tmp_path}/ledger_api.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    init_db(get_engine(url))
    with session_scope(url) as session:
        repo = LedgerRepository(session)
        repo.add_udhaar("Ramesh", 20000)
        repo.record_repayment("Ramesh", 5000)
        repo.add_sale(15000)
    with TestClient(create_app()) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_ledger_endpoint_shape(client: TestClient) -> None:
    body = client.get("/api/ledger").json()
    assert body["customers"] == [
        {"name": "Ramesh", "balance_paise": 15000, "balance": "₹150.00"}
    ]
    assert len(body["transactions"]) == 3
    newest = body["transactions"][0]
    assert {"id", "type", "amount", "amount_paise", "customer", "ts"} <= set(newest)
    assert body["today"]["sales"] == "₹150.00"
    assert body["today"]["cash_in"] == "₹200.00"
