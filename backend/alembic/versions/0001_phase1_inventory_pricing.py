"""phase 1: businesses, users, products, stock-in, stock ledger, pricing, audit

Revision ID: 0001
Revises:
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.migration_helpers import (
    business_id_column,
    fk_column,
    id_column,
    make_append_only,
    qty_column,
    ts_column,
)

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = [
    "users",
    "audit_log",
    "products",
    "stock_movements",
    "stock_in_batches",
    "stock_in_lines",
    "batch_costs",
    "price_history",
    "price_suggestions",
]
LEDGERS = ["stock_movements", "price_history", "audit_log"]


def upgrade() -> None:
    op.create_table(
        "businesses",
        id_column(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("price_rounding", sa.BigInteger, nullable=False),
        sa.Column("price_floor_pct", sa.BigInteger, nullable=False),  # ScaledDecimal(4)
        sa.Column("reprice_threshold_pct", sa.BigInteger, nullable=False),  # ScaledDecimal(4)
        sa.Column("trading_days_per_month", sa.Integer, nullable=False),
        sa.Column("default_allocation_method", sa.String(20), nullable=False),
        ts_column("created_at"),
    )
    op.create_table(
        "users",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("pin_hash", sa.String(200)),
        ts_column("created_at"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "audit_log",
        sa.Column("entity", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("field", sa.String(50), nullable=False),
        sa.Column("old", sa.Text),
        sa.Column("new", sa.Text),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "products",
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("uom", sa.String(20), nullable=False),
        sa.Column("supplier_name", sa.String(200)),
        sa.Column("wac", sa.BigInteger, nullable=False),
        sa.Column("price", sa.BigInteger, nullable=False),
        sa.Column("pricing_mode", sa.String(20), nullable=False),
        sa.Column("target_value", sa.BigInteger),  # ScaledDecimal(4)
        qty_column("reorder_point"),
        sa.Column("lead_time_days", sa.Integer, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        ts_column("created_at"),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "sku"),
    )
    op.create_table(
        "stock_movements",
        fk_column("product_id", "products.id", index=True),
        sa.Column("type", sa.String(30), nullable=False),
        qty_column("qty"),
        sa.Column("unit_cost", sa.BigInteger, nullable=False),
        sa.Column("wac_snapshot", sa.BigInteger, nullable=False),
        sa.Column("ref_type", sa.String(50)),
        sa.Column("ref_id", sa.Uuid()),
        sa.Column("reason", sa.Text),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "stock_in_batches",
        sa.Column("supplier_name", sa.String(200)),
        sa.Column("date", sa.Date, nullable=False),
        sa.Column("allocation_method", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        fk_column("created_by", "users.id"),
        fk_column("posted_by", "users.id", nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        ts_column("created_at"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "stock_in_lines",
        fk_column("batch_id", "stock_in_batches.id", index=True),
        sa.Column("position", sa.Integer, nullable=False),
        fk_column("product_id", "products.id"),
        qty_column("qty"),
        sa.Column("bp", sa.BigInteger, nullable=False),
        sa.Column("allocated_cost", sa.BigInteger),
        sa.Column("landed_unit_cost", sa.BigInteger),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "batch_costs",
        fk_column("batch_id", "stock_in_batches.id", index=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("amount", sa.BigInteger, nullable=False),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("batch_id", "type"),
    )
    op.create_table(
        "price_history",
        fk_column("product_id", "products.id", index=True),
        sa.Column("old_price", sa.BigInteger, nullable=False),
        sa.Column("new_price", sa.BigInteger, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        fk_column("user_id", "users.id"),
        ts_column("ts"),
        business_id_column(),
        id_column(),
    )
    op.create_table(
        "price_suggestions",
        fk_column("product_id", "products.id", index=True),
        sa.Column("suggested_price", sa.BigInteger, nullable=False),
        sa.Column("price_at_suggestion", sa.BigInteger, nullable=False),
        sa.Column("previous_wac", sa.BigInteger, nullable=False),
        sa.Column("trigger_wac", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        fk_column("decided_by", "users.id", nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        ts_column("created_at"),
        business_id_column(),
        id_column(),
    )

    for table in LEDGERS:
        make_append_only(table)


def downgrade() -> None:
    for table in reversed(["businesses", *TENANT_TABLES]):
        op.drop_table(table)
