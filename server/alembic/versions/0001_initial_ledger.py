"""initial ledger: customers + transactions

Revision ID: 0001
Revises:
Create Date: 2026-07-08

"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_normalized", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_customers_name_normalized", "customers", ["name_normalized"], unique=True
    )
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
        sa.Column("ts", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_transactions_type", "transactions", ["type"])
    op.create_index("ix_transactions_customer_id", "transactions", ["customer_id"])
    op.create_index("ix_transactions_ts", "transactions", ["ts"])


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("customers")
