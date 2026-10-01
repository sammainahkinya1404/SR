"""sets bought as one unit and sold as separate items

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.migration_helpers import business_id_column, fk_column, id_column, qty_column, ts_column

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "product_sets",
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("active", sa.Boolean, nullable=False),
        ts_column("created_at"),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "name"),
    )
    op.create_table(
        "set_components",
        fk_column("set_id", "product_sets.id", index=True),
        fk_column("product_id", "products.id"),
        qty_column("qty"),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        business_id_column(),
        id_column(),
        sa.UniqueConstraint("business_id", "product_id"),
    )


def downgrade() -> None:
    op.drop_table("set_components")
    op.drop_table("product_sets")
