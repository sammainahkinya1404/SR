"""Spec Part A §5: sale lines, payments and returns."""

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.money import Cents, to_cents


class PaymentMethod(StrEnum):
    CASH = "cash"
    MPESA = "mpesa"
    CREDIT = "credit"  # needs customer accounts (phase 4)


# M-Pesa transaction codes are 10 uppercase letters/digits, e.g. "SIB2XK7Q9M".
MPESA_CODE = re.compile(r"^[A-Z0-9]{10}$")


@dataclass(frozen=True)
class LineAmounts:
    gross: Cents  # qty x unit price
    net: Cents  # after discount
    cogs: Cents  # qty x WAC at time of sale
    gross_profit: Cents


def line_amounts(qty: Decimal, unit_price: Cents, discount: Cents, wac: Cents) -> LineAmounts:
    gross = to_cents(qty * unit_price)
    if not 0 <= discount <= gross:
        raise ValueError("discount must be between 0 and the line amount")
    net = gross - discount
    cogs = to_cents(qty * wac)
    return LineAmounts(gross=gross, net=net, cogs=cogs, gross_profit=net - cogs)


def below_floor(net: Cents, qty: Decimal, floor_price: Cents) -> bool:
    """True when the effective unit price (net / qty) is under the floor."""
    return Decimal(net) < floor_price * qty


def settle(total: Cents, payments: list[tuple[PaymentMethod, Cents]]) -> Cents:
    """Validate a tender and return the change owed, which is always given in cash.

    Non-cash payments may not exceed the total (there is no way to give M-Pesa change), and the
    tender must cover the total."""
    if any(amount <= 0 for _, amount in payments):
        raise ValueError("payment amounts must be positive")
    non_cash = sum(a for m, a in payments if m is not PaymentMethod.CASH)
    paid = sum(a for _, a in payments)
    if non_cash > total:
        raise ValueError("non-cash payments exceed the sale total")
    if paid < total:
        raise ValueError(f"underpaid by {total - paid} cents")
    return paid - total


def prorate(
    amount: Cents, qty: Decimal, line_qty: Decimal, already_qty: Decimal, already_amount: Cents
) -> Cents:
    """Share of a line amount (refund or COGS) for returning `qty` of `line_qty`.

    The return that brings the line to fully returned takes whatever is left, so repeated partial
    returns never drift from the original amount through rounding."""
    if already_qty + qty == line_qty:
        return amount - already_amount
    return to_cents(Decimal(amount) * qty / line_qty)
