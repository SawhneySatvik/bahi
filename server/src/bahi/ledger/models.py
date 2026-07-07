"""Ledger schema. Money is ALWAYS integer paise; timestamps are naive UTC
(SQLite has no tz type; day summaries convert to the shop timezone at query
time). This module must stay network-free — it is the sovereign core.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

TransactionType = Literal["sale", "udhaar", "repayment"]


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    name_normalized: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    transactions: Mapped[list[Transaction]] = relationship(back_populates="customer")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(16), index=True)  # TransactionType
    amount_paise: Mapped[int] = mapped_column(Integer)
    items: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    customer: Mapped[Customer | None] = relationship(back_populates="transactions")
