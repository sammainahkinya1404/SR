"""phase 2: accounts, cash ledger, sales, payments, returns, receipt numbers

Revision ID: 0002
Revises: 0001
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
    qty_column,
    ts_column,
)

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_TABLES = [
    "accounts",
    "cash_ledger",
    "sales",
    "sale_lines",
    "payments",
    "sale_returns",
    "return_lines",
]
# Written once, never changed. sales (status) and sale_returns (totals) are updated in place.
LEDGERS = ["cash_ledger", "sale_lines", "payments", "return_lines"]


def upgrade() -> None:
    with op.batch_alter_table("businesses") as batch:
        batch.add_column(
            sa.Column("next_receipt_no", sa.BigInteger, nullable=False, server_default="1")
        )

    accounts = op.create_table(
        "accounts",
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        ts_column("created_at"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "cash_ledger",
        fk_column("account_id", "accounts.id", index=True),
        sa.Column("type", sa.String(30), nullable=False),
        money_column("amount"),
        sa.Column("ref_type", sa.String(50)),
        sa.Column("ref_id", sa.Uuid()),
        sa.Column("note", sa.Text),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "sales",
        sa.Column("receipt_no", sa.BigInteger, nullable=False),
        sa.Column("customer_id", sa.Uuid()),
        money_column("subtotal"),
        money_column("discount_total"),
        money_column("total"),
        money_column("cogs"),
        money_column("gross_profit"),
        money_column("change_given"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("device_id", sa.String(100)),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "receipt_no"),
    )
    op.create_table(
        "sale_lines",
        fk_column("sale_id", "sales.id", index=True),
        sa.Column("position", sa.Integer, nullable=False),
        fk_column("product_id", "products.id", index=True),
        qty_column("qty"),
        money_column("unit_price"),
        money_column("discount"),
        money_column("line_total"),
        money_column("wac_snapshot"),
        money_column("cogs"),
        money_column("gross_profit"),
        money_column("floor_price"),
        sa.Column("floor_override", sa.Boolean, nullable=False),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "payments",
        fk_column("sale_id", "sales.id", index=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        money_column("amount"),
        sa.Column("mpesa_code", sa.String(20)),
        fk_column("account_id", "accounts.id"),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "mpesa_code"),
    )
    op.create_table(
        "sale_returns",
        fk_column("sale_id", "sales.id", index=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("refund_method", sa.String(20), nullable=False),
        sa.Column("refund_reference", sa.String(50)),
        money_column("refund_total"),
        money_column("cogs_reversed"),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "return_lines",
        fk_column("return_id", "sale_returns.id", index=True),
        fk_column("sale_line_id", "sale_lines.id", index=True),
        qty_column("qty"),
        money_column("refund"),
        money_column("cogs_reversed"),
        business_id_column(),
        id_column(),
    )
    for table in LEDGERS:
        make_append_only(table)

    # Businesses opened before this migration get the default accounts new ones start with.
    business_ids = op.get_bind().scalars(sa.text("SELECT id FROM businesses")).all()
    now = datetime.now(UTC)
    rows = [
        {
            "id": uuid.uuid4(),
            "business_id": uuid.UUID(bid),
            "type": account_type,
            "name": name,
            "created_at": now,
        }
        for bid in business_ids
        for account_type, name in [
            ("cash", "Cash drawer"),
            ("mpesa", "M-Pesa till"),
            ("bank", "Bank"),
        ]
    ]
    if rows:
        op.bulk_insert(accounts, rows)


def downgrade() -> None:
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
    with op.batch_alter_table("businesses") as batch:
        batch.drop_column("next_receipt_no")
