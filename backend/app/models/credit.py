"""Customer credit (spec Part A §6)."""

import datetime as dt
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, created_at_column


class Customer(TenantMixin, Base):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(20))
    id_number: Mapped[str | None] = mapped_column(String(30))
    credit_limit: Mapped[int]  # cents; 0 = no credit without an owner override
    terms_days: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = created_at_column()


class CreditLedger(TenantMixin, Base):
    """Append-only (DB triggers). amount is signed: charges are positive, everything that reduces
    what the customer owes is negative. A customer's balance is the sum."""

    __tablename__ = "credit_ledger"
    # A repayment's M-Pesa code can only be used once (sales payments are checked too).
    __table_args__ = (UniqueConstraint("business_id", "mpesa_code"),)

    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("customers.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # CreditEntryType
    amount: Mapped[int]
    due_date: Mapped[dt.date | None]  # charges only
    sale_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sales.id"))
    ref_type: Mapped[str | None] = mapped_column(String(50))
    ref_id: Mapped[uuid.UUID | None]
    # Repayments: where the money went.
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    mpesa_code: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()


class CreditAllocation(TenantMixin, Base):
    """How much of a reducing entry (repayment, write-off, credit note) cleared which charge.
    Append-only. A charge's outstanding amount is its amount minus its allocations."""

    __tablename__ = "credit_allocations"

    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_ledger.id"), index=True)
    charge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("credit_ledger.id"), index=True)
    amount: Mapped[int]


class SmsOutbox(TenantMixin, Base):
    """Messages waiting for an SMS gateway (not integrated yet). One per kind per reference, so
    re-running the reminder job never double-sends."""

    __tablename__ = "sms_outbox"
    __table_args__ = (UniqueConstraint("business_id", "kind", "ref_id"),)

    phone: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30))  # ReminderKind
    ref_type: Mapped[str] = mapped_column(String(50))
    ref_id: Mapped[uuid.UUID]
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / sent / failed
    created_at: Mapped[datetime] = created_at_column()
    sent_at: Mapped[datetime | None]
