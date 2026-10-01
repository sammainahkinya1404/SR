"""Spec Part A §9-10: periods, profit figures, break-even, turnover and stock-value replay."""

import calendar
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID

from app.domain.clock import EAT
from app.domain.money import Cents, to_cents

# Periods ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Period:
    start: date
    end: date  # inclusive

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def dates(self) -> list[date]:
        return [self.start + timedelta(days=i) for i in range(self.days)]

    def utc_bounds(self) -> tuple[datetime, datetime]:
        """[start, end) in UTC for filtering stored timestamps by Kenyan business dates."""
        return day_start_utc(self.start), day_start_utc(self.end + timedelta(days=1))


def day_start_utc(d: date) -> datetime:
    return datetime.combine(d, time(), EAT).astimezone(UTC)


def dashboard_periods(today: date) -> dict[str, tuple[Period, Period]]:
    """Each dashboard period with the like-for-like period it is compared to: today vs
    yesterday, week-to-date vs the same days last week, month-to-date vs the same days of last
    month (clamped to that month's length)."""
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    prev_month_end = month_start - timedelta(days=1)
    prev_month_start = prev_month_end.replace(day=1)
    prev_month_to = prev_month_start.replace(day=min(today.day, prev_month_end.day))
    yesterday = today - timedelta(days=1)
    return {
        "today": (Period(today, today), Period(yesterday, yesterday)),
        "week": (
            Period(week_start, today),
            Period(week_start - timedelta(days=7), today - timedelta(days=7)),
        ),
        "month": (Period(month_start, today), Period(prev_month_start, prev_month_to)),
    }


# Figures ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Figures:
    sales: Cents  # net of refunds
    cogs: Cents  # net of cost reversed by returns
    opex: Cents  # all expenses incl. automatic losses and bad debt
    fixed_opex: Cents

    @property
    def gross_profit(self) -> Cents:
        return self.sales - self.cogs

    @property
    def net_profit(self) -> Cents:
        return self.gross_profit - self.opex

    @property
    def gross_margin(self) -> Decimal | None:
        return None if self.sales <= 0 else Decimal(self.gross_profit) / self.sales


def ratio(numerator: int, denominator: Decimal | int) -> Decimal | None:
    return (
        None if not denominator or denominator <= 0 else Decimal(numerator) / Decimal(denominator)
    )


def change_pct(current: Decimal | int | None, previous: Decimal | int | None) -> Decimal | None:
    """Relative change for a trend arrow; None when there is nothing to compare against."""
    if current is None or previous is None or previous == 0:
        return None
    return (Decimal(current) - Decimal(previous)) / abs(Decimal(previous))


def average(values: Sequence[int]) -> Cents:
    return to_cents(Decimal(sum(values)) / len(values)) if values else 0


# Break-even -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BreakEven:
    monthly_fixed_costs: Cents
    gross_margin: Decimal | None  # trailing 30 days
    monthly: Cents | None  # None when there is no margin to cover costs with
    daily: Cents | None
    month_to_date_sales: Cents
    pro_rata_target: Cents | None

    @property
    def below(self) -> bool:
        return self.pro_rata_target is not None and self.month_to_date_sales < self.pro_rata_target


def break_even(
    *,
    monthly_fixed_costs: Cents,
    gross_margin: Decimal | None,
    trading_days: int,
    today: date,
    month_to_date_sales: Cents,
) -> BreakEven:
    """monthly = fixed costs / gross margin %, daily = monthly / trading days, and the
    month-to-date target is the monthly figure pro-rated by calendar days elapsed."""
    if gross_margin is None or gross_margin <= 0:
        return BreakEven(monthly_fixed_costs, gross_margin, None, None, month_to_date_sales, None)
    monthly = to_cents(monthly_fixed_costs / gross_margin)
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    return BreakEven(
        monthly_fixed_costs,
        gross_margin,
        monthly,
        to_cents(Decimal(monthly) / trading_days),
        month_to_date_sales,
        to_cents(Decimal(monthly) * today.day / days_in_month),
    )


def monthly_equivalent(amount: Cents, frequency: str) -> Cents:
    """A recurring amount as a monthly figure (weekly x 52 / 12)."""
    return amount if frequency == "monthly" else to_cents(Decimal(amount) * 52 / 12)


# Stock value replay -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Movement:
    product_id: UUID
    qty: Decimal  # signed
    wac_after: Cents  # the product's WAC once this movement was posted
    ts: datetime  # UTC


def stock_values(
    movements: Iterable[Movement], boundaries: Sequence[datetime], per_product: bool = False
) -> list[Cents] | dict[UUID, list[Cents]]:
    """Stock value (qty on hand x WAC) at each boundary, replayed from the ledger.

    Every movement records the WAC after it, so the value at any past moment is exact without
    stored snapshots. `movements` must be in time order; `boundaries` ascending."""
    qty: dict[UUID, Decimal] = {}
    wac: dict[UUID, int] = {}
    series: dict[UUID, list[Cents]] = {}
    totals: list[Cents] = []
    pending = iter(movements)
    nxt = next(pending, None)
    for boundary in boundaries:
        while nxt is not None and nxt.ts < boundary:
            qty[nxt.product_id] = qty.get(nxt.product_id, Decimal(0)) + nxt.qty
            wac[nxt.product_id] = nxt.wac_after
            nxt = next(pending, None)
        values = {pid: to_cents(q * wac[pid]) for pid, q in qty.items()}
        if per_product:
            for pid in qty:
                series.setdefault(pid, [0] * len(totals))
            for pid, row in series.items():
                row.append(values.get(pid, 0))
        totals.append(sum(values.values()))
    return series if per_product else totals


def turnover(cogs: Cents, average_stock_value: Cents) -> Decimal | None:
    """COGS / average stock value for the period (not annualised)."""
    return ratio(cogs, average_stock_value)


def days_of_stock(average_stock_value: Cents, cogs: Cents, days: int) -> Decimal | None:
    """average stock value / average daily COGS"""
    return ratio(average_stock_value * days, cogs)
