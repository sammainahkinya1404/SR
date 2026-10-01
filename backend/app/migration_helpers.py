"""Helpers shared by migrations. Column helpers mirror the ORM mixins and types in app/models."""

import sqlalchemy as sa
from alembic import op


def id_column() -> sa.Column:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def business_id_column() -> sa.Column:
    return sa.Column(
        "business_id", sa.Uuid(), sa.ForeignKey("businesses.id"), nullable=False, index=True
    )


def fk_column(name: str, target: str, nullable: bool = False, index: bool = False) -> sa.Column:
    return sa.Column(name, sa.Uuid(), sa.ForeignKey(target), nullable=nullable, index=index)


def ts_column(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False)


def qty_column(name: str) -> sa.Column:
    # ScaledDecimal(3): thousandths of a unit.
    return sa.Column(name, sa.BigInteger, nullable=False)


def money_column(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.BigInteger, nullable=nullable)


def make_append_only(table: str) -> None:
    """Ledgers are insert-only: block UPDATE and DELETE in the database itself (spec Part B §3)."""
    for action in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER {table}_no_{action.lower()} BEFORE {action} ON {table} "
            f"BEGIN SELECT RAISE(ABORT, '{table} is append-only: post a reversal instead'); END"
        )
