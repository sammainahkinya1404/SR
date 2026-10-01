"""phase 4: customers, credit ledger + allocations, SMS outbox; credit payments

Revision ID: 0004
Revises: 0003
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

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = ["customers", "credit_ledger", "credit_allocations", "sms_outbox"]
LEDGERS = ["credit_ledger", "credit_allocations"]


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("id_number", sa.String(30)),
        money_column("credit_limit"),
        sa.Column("terms_days", sa.Integer, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        ts_column("created_at"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "credit_ledger",
        fk_column("customer_id", "customers.id", index=True),
        sa.Column("type", sa.String(20), nullable=False),
        money_column("amount"),
        sa.Column("due_date", sa.Date),
        fk_column("sale_id", "sales.id", nullable=True),
        sa.Column("ref_type", sa.String(50)),
        sa.Column("ref_id", sa.Uuid()),
        fk_column("account_id", "accounts.id", nullable=True),
        sa.Column("mpesa_code", sa.String(20)),
        sa.Column("note", sa.Text),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "mpesa_code"),
    )
    op.create_table(
        "credit_allocations",
        fk_column("entry_id", "credit_ledger.id", index=True),
        fk_column("charge_id", "credit_ledger.id", index=True),
        money_column("amount"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "sms_outbox",
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("ref_type", sa.String(50), nullable=False),
        sa.Column("ref_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        ts_column("created_at"),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "kind", "ref_id"),
    )
    for table in LEDGERS:
        make_append_only(table)

    with op.batch_alter_table("sales") as batch:
        batch.create_foreign_key("fk_sales_customer_id", "customers", ["customer_id"], ["id"])
        batch.create_index("ix_sales_customer_id", ["customer_id"])

    # Credit payments have no account. SQLite rebuilds the table for this, which drops its
    # append-only triggers, so they are recreated.
    with op.batch_alter_table("payments") as batch:
        batch.alter_column("account_id", existing_type=sa.Uuid(), nullable=True)
    make_append_only("payments")

    # Businesses opened before this migration get the new system category.
    categories = sa.table(
        "expense_categories",
        sa.column("id", sa.Uuid()),
        sa.column("business_id", sa.Uuid()),
        sa.column("name", sa.String),
        sa.column("is_fixed", sa.Boolean),
        sa.column("system", sa.Boolean),
        sa.column("active", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    business_ids = op.get_bind().scalars(sa.text("SELECT id FROM businesses")).all()
    now = datetime.now(UTC)
    rows = [
        {
            "id": uuid.uuid4(),
            "business_id": uuid.UUID(bid),
            "name": "Bad debt",
            "is_fixed": False,
            "system": True,
            "active": True,
            "created_at": now,
        }
        for bid in business_ids
    ]
    if rows:
        op.bulk_insert(categories, rows)


def downgrade() -> None:
    op.execute("DELETE FROM expense_categories WHERE name = 'Bad debt' AND system = 1")
    with op.batch_alter_table("payments") as batch:
        batch.alter_column("account_id", existing_type=sa.Uuid(), nullable=False)
    make_append_only("payments")
    with op.batch_alter_table("sales") as batch:
        batch.drop_index("ix_sales_customer_id")
        batch.drop_constraint("fk_sales_customer_id", type_="foreignkey")
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
