"""Plain-text receipts: 32 columns, which fits 58 mm thermal printers and reads well in
SMS/WhatsApp. Sending them is an integration for later; this only renders the text."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.domain.clock import EAT

WIDTH = 32


def ksh(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, part = divmod(abs(cents), 100)
    return f"{sign}{whole:,}.{part:02d}"


def receipt_number(n: int) -> str:
    return f"{n:06d}"


def _qty(q: Decimal) -> str:
    return format(q.normalize(), "f")


def _row(left: str, right: str) -> str:
    room = WIDTH - len(right) - 1
    return f"{left[:room]:<{room}} {right}"


@dataclass(frozen=True)
class ReceiptLine:
    name: str
    qty: Decimal
    unit_price: int
    discount: int
    line_total: int


@dataclass(frozen=True)
class ReceiptPayment:
    method: str
    amount: int
    reference: str | None


def render(
    *,
    business_name: str,
    receipt_no: int,
    ts: datetime,
    cashier: str,
    lines: list[ReceiptLine],
    total: int,
    payments: list[ReceiptPayment],
    change: int,
    refunded: int,
    customer: str | None = None,
) -> str:
    if ts.tzinfo is None:  # SQLite hands timestamps back naive; they are stored in UTC
        ts = ts.replace(tzinfo=UTC)
    rule = "-" * WIDTH
    out = [
        business_name[:WIDTH].center(WIDTH).rstrip(),
        _row(
            f"Receipt {receipt_number(receipt_no)}", ts.astimezone(EAT).strftime("%d/%m/%Y %H:%M")
        ),
        f"Served by {cashier}"[:WIDTH],
        *([f"Customer: {customer}"[:WIDTH]] if customer else []),
        rule,
    ]
    for line in lines:
        out.append(line.name[:WIDTH])
        out.append(
            _row(
                f"  {_qty(line.qty)} x {ksh(line.unit_price)}", ksh(line.line_total + line.discount)
            )
        )
        if line.discount:
            out.append(_row("  Discount", ksh(-line.discount)))
    out += [rule, _row("TOTAL KSh", ksh(total))]
    labels = {"cash": "Cash", "mpesa": "M-Pesa", "credit": "Credit"}
    for p in payments:
        label = labels.get(p.method, p.method)
        out.append(_row(f"{label} {p.reference}" if p.reference else label, ksh(p.amount)))
    if change:
        out.append(_row("Change", ksh(change)))
    if refunded:
        out.append(_row("Refunded", ksh(-refunded)))
    out += [rule, "Thank you!".center(WIDTH).rstrip()]
    return "\n".join(out)
