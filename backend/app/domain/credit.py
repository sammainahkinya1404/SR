"""Spec Part A §6: customer credit."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from app.domain.money import Cents
from app.domain.receipts import ksh


class CreditEntryType(StrEnum):
    CHARGE = "charge"  # a credit sale: the invoice
    REPAYMENT = "repayment"
    WRITEOFF = "writeoff"
    CREDIT_NOTE = "credit_note"  # goods returned from a credit sale


@dataclass(frozen=True)
class OpenInvoice:
    charge_id: UUID
    due_date: date
    outstanding: Cents


def allocate(
    invoices: list[OpenInvoice], amount: Cents, prefer: UUID | None = None
) -> list[tuple[UUID, Cents]]:
    """Spread a reduction (repayment, write-off, credit note) over open invoices, oldest first.

    `invoices` must already be oldest-first. `prefer` puts one invoice at the front, so a return
    clears its own sale's invoice before older ones."""
    total = sum(i.outstanding for i in invoices)
    if amount <= 0:
        raise ValueError("amount must be positive")
    if amount > total:
        raise ValueError(f"amount is more than the {total} outstanding")
    ordered = sorted(invoices, key=lambda i: i.charge_id != prefer) if prefer else invoices
    parts = []
    for invoice in ordered:
        if amount == 0:
            break
        take = min(amount, invoice.outstanding)
        if take:
            parts.append((invoice.charge_id, take))
            amount -= take
    return parts


class AgeingBucket(StrEnum):
    CURRENT = "current"
    DAYS_1_30 = "1-30"
    DAYS_31_60 = "31-60"
    DAYS_61_90 = "61-90"
    DAYS_90_PLUS = "90+"


def days_overdue(due_date: date, today: date) -> int:
    return (today - due_date).days


def bucket(due_date: date, today: date) -> AgeingBucket:
    days = days_overdue(due_date, today)
    if days <= 0:
        return AgeingBucket.CURRENT
    if days <= 30:
        return AgeingBucket.DAYS_1_30
    if days <= 60:
        return AgeingBucket.DAYS_31_60
    if days <= 90:
        return AgeingBucket.DAYS_61_90
    return AgeingBucket.DAYS_90_PLUS


def ageing(invoices: list[OpenInvoice], today: date) -> dict[AgeingBucket, Cents]:
    totals = dict.fromkeys(AgeingBucket, 0)
    for invoice in invoices:
        totals[bucket(invoice.due_date, today)] += invoice.outstanding
    return totals


def credit_blocks(balance: Cents, limit: Cents, new_charge: Cents, overdue: Cents) -> list[str]:
    """Why a credit sale must be blocked (empty = allowed). The owner can override."""
    reasons = []
    if balance + new_charge > limit:
        reasons.append(f"balance would be {ksh(balance + new_charge)}, over the {ksh(limit)} limit")
    if overdue > 0:
        reasons.append(f"{ksh(overdue)} is overdue")
    return reasons


class ReminderKind(StrEnum):
    DUE = "credit_due"
    OVERDUE = "credit_overdue"


def reminder_kind(due_date: date, today: date) -> ReminderKind | None:
    """Reminders go out on the due date and once the invoice becomes overdue."""
    if due_date == today:
        return ReminderKind.DUE
    if due_date < today:
        return ReminderKind.OVERDUE
    return None


def reminder_message(
    kind: ReminderKind,
    *,
    business_name: str,
    customer_name: str,
    receipt_no: str,
    outstanding: Cents,
    due_date: date,
    balance: Cents,
) -> str:
    when = "is due today" if kind is ReminderKind.DUE else f"was due on {due_date:%d/%m/%Y}"
    return (
        f"Dear {customer_name}, KSh {ksh(outstanding)} on receipt {receipt_no} {when}. "
        f"Your total balance is KSh {ksh(balance)}. Thank you, {business_name}."
    )
