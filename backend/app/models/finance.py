"""Expenses, transfers, owner capital/drawings and cash-ups (spec Part A §7-8)."""

import datetime as dt
import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, created_at_column


class ExpenseCategory(TenantMixin, Base):
    __tablename__ = "expense_categories"
    __table_args__ = (UniqueConstraint("business_id", "name"),)

    name: Mapped[str] = mapped_column(String(100))
    # Default for expenses in this category; fixed costs drive break-even (spec Part A §9).
    is_fixed: Mapped[bool]
    # System categories receive automatic postings (stock loss, cash shortage) and can't be
    # chosen for manual expenses.
    system: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = created_at_column()


class Expense(TenantMixin, Base):
    """Append-only (enforced by DB triggers). A mistake is fixed by a reversal row with the
    opposite amount and `reverses_id` pointing at the original."""

    __tablename__ = "expenses"
    __table_args__ = (
        # A recurring expense posts at most once per scheduled date.
        UniqueConstraint("business_id", "recurring_id", "date"),
        UniqueConstraint("business_id", "reverses_id"),
    )

    date: Mapped[dt.date]
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expense_categories.id"), index=True)
    amount: Mapped[int]  # signed: reversals are negative
    # None for non-cash losses (stock written off): they cost money but none leaves an account.
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    is_fixed: Mapped[bool]
    note: Mapped[str | None] = mapped_column(Text)
    receipt_url: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(30))  # ExpenseSource
    ref_type: Mapped[str | None] = mapped_column(String(50))
    ref_id: Mapped[uuid.UUID | None]
    recurring_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("recurring_expenses.id"))
    reverses_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("expenses.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()


class RecurringExpense(TenantMixin, Base):
    """A schedule, not a ledger: amount, account and active flag can change (changes audited)."""

    __tablename__ = "recurring_expenses"

    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("expense_categories.id"))
    amount: Mapped[int]
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    is_fixed: Mapped[bool]
    note: Mapped[str | None] = mapped_column(Text)
    frequency: Mapped[str] = mapped_column(String(20))  # Frequency
    day: Mapped[int] = mapped_column(Integer)
    next_due: Mapped[dt.date]
    active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = created_at_column()


class Transfer(TenantMixin, Base):
    """Money moved between accounts, e.g. banking the day's cash. Append-only."""

    __tablename__ = "transfers"

    date: Mapped[dt.date]
    from_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    to_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    amount: Mapped[int]  # arrives in the destination account
    fee: Mapped[int]  # charged on top to the source account, posted as an expense
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()


class OwnerEntry(TenantMixin, Base):
    """Owner capital and drawings: equity movements, never income or expenses. Append-only."""

    __tablename__ = "owner_entries"

    type: Mapped[str] = mapped_column(String(20))  # OwnerEntryType
    date: Mapped[dt.date]
    amount: Mapped[int]  # positive; the type gives the direction
    # None for drawings in kind (stock taken for personal use, valued at WAC).
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()


class CashUp(TenantMixin, Base):
    """One count per account per day. Append-only."""

    __tablename__ = "cash_ups"
    __table_args__ = (UniqueConstraint("business_id", "account_id", "date"),)

    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id"))
    date: Mapped[dt.date]
    expected: Mapped[int]
    counted: Mapped[int]
    variance: Mapped[int]  # counted - expected
    explanation: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()
