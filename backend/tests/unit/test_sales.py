from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.receipts import ReceiptLine, ReceiptPayment, ksh, render
from app.domain.sales import PaymentMethod, below_floor, line_amounts, prorate, settle

CASH, MPESA = PaymentMethod.CASH, PaymentMethod.MPESA


def test_line_amounts_snapshot_cost_and_profit():
    a = line_amounts(Decimal(2), unit_price=15_000, discount=1_000, wac=10_000)
    assert (a.gross, a.net, a.cogs, a.gross_profit) == (30_000, 29_000, 20_000, 9_000)


def test_fractional_quantities_round_to_the_cent():
    a = line_amounts(Decimal("0.333"), unit_price=1_000, discount=0, wac=999)
    assert (a.net, a.cogs) == (333, 333)  # 333.0 and 332.667


@pytest.mark.parametrize("discount", [-1, 30_001])
def test_discount_must_fit_the_line(discount):
    with pytest.raises(ValueError):
        line_amounts(Decimal(2), unit_price=15_000, discount=discount, wac=0)


def test_below_floor_uses_effective_unit_price():
    assert below_floor(net=21_999, qty=Decimal(2), floor_price=11_000)
    assert not below_floor(net=22_000, qty=Decimal(2), floor_price=11_000)


def test_settle_gives_change_from_cash_only():
    assert settle(29_000, [(CASH, 30_000)]) == 1_000
    assert settle(15_000, [(MPESA, 10_000), (CASH, 5_000)]) == 0
    assert settle(0, []) == 0


@pytest.mark.parametrize(
    "payments, message",
    [
        ([(CASH, 1_000)], "underpaid"),
        ([(MPESA, 16_000)], "non-cash"),
        ([(CASH, 0)], "positive"),
    ],
)
def test_settle_rejects_bad_tenders(payments, message):
    with pytest.raises(ValueError, match=message):
        settle(15_000, payments)


def test_prorate_never_drifts_across_partial_returns():
    first = prorate(44_000, Decimal(1), Decimal(3), Decimal(0), 0)
    second = prorate(44_000, Decimal(1), Decimal(3), Decimal(1), first)
    last = prorate(44_000, Decimal(1), Decimal(3), Decimal(2), first + second)
    assert (first, second, last) == (14_667, 14_667, 14_666)
    assert first + second + last == 44_000


def test_ksh_formatting():
    assert ksh(123_456_78) == "123,456.78"
    assert ksh(-1_000) == "-10.00"
    assert ksh(5) == "0.05"


def test_receipt_fits_32_columns_and_uses_kenya_time():
    text = render(
        business_name="Mama Mboga Supermarket and General Stores",
        receipt_no=42,
        ts=datetime(2026, 9, 29, 11, 5, tzinfo=UTC),
        cashier="Wanjiku",
        lines=[ReceiptLine("Rice 1kg", Decimal("2.000"), 15_000, 1_000, 29_000)],
        total=29_000,
        payments=[
            ReceiptPayment("mpesa", 20_000, "SIB2XK7Q9M"),
            ReceiptPayment("cash", 10_000, None),
        ],
        change=1_000,
        refunded=0,
    )
    assert all(len(row) <= 32 for row in text.splitlines())
    assert "Receipt 000042" in text
    assert "29/09/2026 14:05" in text  # 11:05 UTC is 14:05 EAT
    assert "  2 x 150.00" in text
    assert "M-Pesa SIB2XK7Q9M" in text
    assert text.splitlines()[-3].endswith("10.00")  # change
