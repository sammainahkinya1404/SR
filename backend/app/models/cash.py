import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, created_at_column


class Account(TenantMixin, Base):
    """Where money sits: cash drawer, M-Pesa till, bank (spec Part A §8)."""

    __tablename__ = "accounts"

    type: Mapped[str] = mapped_column(String(20))  # AccountType
    name: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = created_at_column()


class CashLedger(TenantMixin, Base):
    """Append-only (enforced by DB triggers). Balances are always summed from here.
    amount is signed: money in is positive."""

    __tablename__ = "cash_ledger"

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))  # CashEntryType
    amount: Mapped[int]
    ref_type: Mapped[str | None] = mapped_column(String(50))
    ref_id: Mapped[uuid.UUID | None]
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()
