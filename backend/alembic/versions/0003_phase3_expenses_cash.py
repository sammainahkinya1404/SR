"""phase 3: expense categories, expenses, recurring expenses, transfers, owner entries, cash-ups

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-29
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from app.migration_helpers import (
    business_id_column,
    fk_column,
    id_column,
    make_append_only,
    money_column,
    ts_column,
)

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = [
    "expense_categories",
    "recurring_expenses",
    "expenses",
    "transfers",
    "owner_entries",
    "cash_ups",
]
LEDGERS = ["expenses", "transfers", "owner_entries", "cash_ups"]

# Mirrors app.services.expenses at the time of this migration (migrations must not import
# service code that may change later).
DEFAULT_CATEGORIES = [
    ("Rent", True, False),
    ("Salaries", True, False),
    ("Electricity", True, False),
    ("Internet", True, False),
    ("Transport", False, False),
    ("M-Pesa charges", False, False),
    ("Packaging", False, False),
    ("Repairs", False, False),
    ("Other", False, False),
    ("Stock loss", False, True),
    ("Cash shortage", False, True),
]


def upgrade() -> None:
    categories = op.create_table(
        "expense_categories",
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_fixed", sa.Boolean, nullable=False),
        sa.Column("system", sa.Boolean, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        ts_column("created_at"),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "name"),
    )
    op.create_table(
        "recurring_expenses",
        fk_column("category_id", "expense_categories.id"),
        money_column("amount"),
        fk_column("account_id", "accounts.id"),
        sa.Column("is_fixed", sa.Boolean, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("frequency", sa.String(20), nullable=False),
        sa.Column("day", sa.Integer, nullable=False),
        sa.Column("next_due", sa.Date, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        fk_column("created_by", "users.id"),
        ts_column("created_at"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "expenses",
        sa.Column("date", sa.Date, nullable=False),
        fk_column("category_id", "expense_categories.id", index=True),
        money_column("amount"),
        fk_column("account_id", "accounts.id", nullable=True),
        sa.Column("is_fixed", sa.Boolean, nullable=False),
        sa.Column("note", sa.Text),
        sa.Column("receipt_url", sa.String(500)),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("ref_type", sa.String(50)),
        sa.Column("ref_id", sa.Uuid()),
        fk_column("recurring_id", "recurring_expenses.id", nullable=True),
        fk_column("reverses_id", "expenses.id", nullable=True),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "recurring_id", "date"),
        sa.UniqueConstraint("business_id", "reverses_id"),
    )
    op.create_table(
        "transfers",
        sa.Column("date", sa.Date, nullable=False),
        fk_column("from_account_id", "accounts.id"),
        fk_column("to_account_id", "accounts.id"),
        money_column("amount"),
        money_column("fee"),
        sa.Column("note", sa.Text),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "owner_entries",
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("date", sa.Date, nullable=False),
        money_column("amount"),
        fk_column("account_id", "accounts.id", nullable=True),
        sa.Column("note", sa.Text),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "cash_ups",
        fk_column("account_id", "accounts.id"),
        sa.Column("date", sa.Date, nullable=False),
        money_column("expected"),
        money_column("counted"),
        money_column("variance"),
        sa.Column("explanation", sa.Text),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "account_id", "date"),
    )
    for table in LEDGERS:
        make_append_only(table)

    # Businesses opened before this migration get the categories new ones start with.
    business_ids = op.get_bind().scalars(sa.text("SELECT id FROM businesses")).all()
    now = datetime.now(UTC)
    rows = [
        {
            "id": uuid.uuid4(),
            "business_id": uuid.UUID(bid),
            "name": name,
            "is_fixed": is_fixed,
            "system": system,
            "active": True,
            "created_at": now,
        }
        for bid in business_ids
        for name, is_fixed, system in DEFAULT_CATEGORIES
    ]
    if rows:
        op.bulk_insert(categories, rows)


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
