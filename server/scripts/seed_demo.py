"""Seed a small, believable kirana day so the Alexa+ demo has real rows.

Usage: .venv/bin/python scripts/seed_demo.py   (writes to DATABASE_URL, default sqlite:///bahi.db)
Idempotent enough for a demo: skips if the ledger already has transactions.
"""

from __future__ import annotations

from bahi.config import get_settings
from bahi.ledger.db import init_db, session_scope
from bahi.ledger.repository import LedgerRepository


def main() -> None:
    init_db()
    with session_scope() as session:
        repo = LedgerRepository(session, tz=get_settings().tz)
        if repo.recent_transactions(1):
            print("ledger already has entries; not seeding")
            return
        repo.add_sale(
            4_50_00,
            [
                {"name": "Atta 5kg", "qty": 1, "unit_price_paise": 2_80_00},
                {"name": "Toor dal 1kg", "qty": 1, "unit_price_paise": 1_70_00},
            ],
        )
        repo.add_sale(1_20_00, [{"name": "Milk 1L", "qty": 2, "unit_price_paise": 60_00}])
        repo.add_sale(
            85_00,
            [
                {"name": "Parle-G", "qty": 5, "unit_price_paise": 10_00},
                {"name": "Maggi", "qty": 2, "unit_price_paise": 17_50},
            ],
        )
        repo.add_udhaar("Ramesh", 2_00_00, note="ration")
        repo.add_udhaar("Sunita", 6_40_00, note="monthly groceries")
        repo.add_udhaar("Mohan", 1_10_00)
        repo.record_repayment("Sunita", 1_50_00)
    print("seeded demo ledger")


if __name__ == "__main__":
    main()
