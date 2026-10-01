"""per-item minimum price (bottom of the price range)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("min_price", sa.BigInteger, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("products") as batch:
        batch.drop_column("min_price")
