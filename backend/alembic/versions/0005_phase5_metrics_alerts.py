"""phase 5: metric snapshots, alerts, alert threshold settings

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.migration_helpers import business_id_column, id_column, money_column, ts_column

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Defaults in stored units: Fraction columns are ScaledDecimal(4), so 0.20 is stored as 2000.
SETTINGS = [
    ("default_target_margin", sa.BigInteger, "2000"),
    ("alert_low_cash_days", sa.Integer, "7"),
    ("alert_credit_risk_pct", sa.BigInteger, "1000"),
    ("alert_slow_moving_days", sa.Integer, "30"),
    ("alert_max_days_of_stock", sa.Integer, "90"),
]


def upgrade() -> None:
    with op.batch_alter_table("businesses") as batch:
        for name, type_, default in SETTINGS:
            batch.add_column(sa.Column(name, type_, nullable=False, server_default=default))

    op.create_table(
        "metric_snapshots",
        sa.Column("date", sa.Date, nullable=False),
        money_column("sales"),
        money_column("cogs"),
        money_column("gross_profit"),
        money_column("opex"),
        money_column("net_profit"),
        money_column("stock_value"),
        money_column("cash"),
        ts_column("computed_at"),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "date"),
    )
    op.create_table(
        "alerts",
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.Uuid()),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        ts_column("created_at"),
        ts_column("updated_at"),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        business_id_column(),
        id_column(),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("metric_snapshots")
    with op.batch_alter_table("businesses") as batch:
        for name, _, _ in reversed(SETTINGS):
            batch.drop_column(name)
