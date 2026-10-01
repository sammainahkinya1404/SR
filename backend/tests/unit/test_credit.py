import uuid
from datetime import date

import pytest

from app.domain.credit import (
    AgeingBucket,
    OpenInvoice,
    ReminderKind,
    ageing,
    allocate,
    bucket,
    credit_blocks,
    reminder_kind,
    reminder_message,
)

A, B, C = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
INVOICES = [
    OpenInvoice(A, date(2026, 7, 1), 30_000),
    OpenInvoice(B, date(2026, 8, 1), 15_000),
    OpenInvoice(C, date(2026, 9, 1), 5_000),
]


def test_repayments_clear_the_oldest_invoices_first():
    assert allocate(INVOICES, 35_000) == [(A, 30_000), (B, 5_000)]
    assert allocate(INVOICES, 50_000) == [(A, 30_000), (B, 15_000), (C, 5_000)]


def test_preferred_invoice_is_cleared_first():
    assert allocate(INVOICES, 8_000, prefer=C) == [(C, 5_000), (A, 3_000)]


@pytest.mark.parametrize("amount", [0, -1, 50_001])
def test_allocation_rejects_nothing_or_more_than_owed(amount):
    with pytest.raises(ValueError):
        allocate(INVOICES, amount)


@pytest.mark.parametrize(
    "due, expected",
    [
        (date(2026, 9, 29), AgeingBucket.CURRENT),  # due today is not overdue
        (date(2026, 10, 5), AgeingBucket.CURRENT),
        (date(2026, 9, 28), AgeingBucket.DAYS_1_30),
        (date(2026, 8, 30), AgeingBucket.DAYS_1_30),  # 30 days
        (date(2026, 8, 29), AgeingBucket.DAYS_31_60),
        (date(2026, 7, 1), AgeingBucket.DAYS_61_90),  # 90 days
        (date(2026, 6, 30), AgeingBucket.DAYS_90_PLUS),
    ],
)
def test_ageing_buckets(due, expected):
    assert bucket(due, date(2026, 9, 29)) == expected


def test_ageing_totals():
    totals = ageing(INVOICES, date(2026, 9, 29))
    assert totals == {
        AgeingBucket.CURRENT: 0,
        AgeingBucket.DAYS_1_30: 5_000,
        AgeingBucket.DAYS_31_60: 15_000,
        AgeingBucket.DAYS_61_90: 30_000,
        AgeingBucket.DAYS_90_PLUS: 0,
    }


def test_credit_blocks():
    assert credit_blocks(balance=30_000, limit=50_000, new_charge=20_000, overdue=0) == []
    over = credit_blocks(balance=30_000, limit=50_000, new_charge=20_001, overdue=0)
    assert over == ["balance would be 500.01, over the 500.00 limit"]
    assert credit_blocks(balance=100, limit=50_000, new_charge=100, overdue=100) == [
        "1.00 is overdue"
    ]


def test_reminders_go_out_on_the_due_date_and_once_overdue():
    today = date(2026, 9, 29)
    assert reminder_kind(date(2026, 9, 29), today) is ReminderKind.DUE
    assert reminder_kind(date(2026, 9, 1), today) is ReminderKind.OVERDUE
    assert reminder_kind(date(2026, 10, 1), today) is None


def test_reminder_message_fits_one_sms():
    text = reminder_message(
        ReminderKind.OVERDUE,
        business_name="Mama Mboga Stores",
        customer_name="Wanjiku Kamau",
        receipt_no="000123",
        outstanding=150_000,
        due_date=date(2026, 9, 1),
        balance=250_000,
    )
    assert text == (
        "Dear Wanjiku Kamau, KSh 1,500.00 on receipt 000123 was due on 01/09/2026. "
        "Your total balance is KSh 2,500.00. Thank you, Mama Mboga Stores."
    )
    assert len(text) <= 160
