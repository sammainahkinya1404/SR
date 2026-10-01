"""Profit, break-even, turnover, product ranking and the dashboard (spec Part A §9-10, Part B §8).

Every figure is computed from the ledgers. `metric_snapshots` only caches finished days for the
daily history. SQLite has no materialised views, so reports are computed on request; bucketing
by Kenyan business date is done in Python, which is fine at a shop's volume."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.domain import metrics as m
from app.domain.clock import business_today
from app.domain.metrics import Figures, Period
from app.models import (
    Business,
    CashLedger,
    Expense,
    MetricSnapshot,
    Product,
    RecurringExpense,
    ReturnLine,
    Sale,
    SaleLine,
    SaleReturn,
    StockMovement,
)


def as_utc(ts: datetime) -> datetime:
    # SQLite returns stored UTC timestamps without tzinfo.
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def _day(ts: datetime) -> date:
    return business_today(as_utc(ts))


def trailing(today: date, days: int = 30) -> Period:
    return Period(today - timedelta(days=days - 1), today)


# Profit figures ---------------------------------------------------------------------------------


def figures(session: Session, period: Period) -> Figures:
    session.flush()
    start, end = period.utc_bounds()
    sales, cogs = session.execute(
        select(func.coalesce(func.sum(Sale.total), 0), func.coalesce(func.sum(Sale.cogs), 0)).where(
            Sale.ts >= start, Sale.ts < end
        )
    ).one()
    refunds, cogs_back = session.execute(
        select(
            func.coalesce(func.sum(SaleReturn.refund_total), 0),
            func.coalesce(func.sum(SaleReturn.cogs_reversed), 0),
        ).where(SaleReturn.ts >= start, SaleReturn.ts < end)
    ).one()
    opex, fixed = session.execute(
        select(
            func.coalesce(func.sum(Expense.amount), 0),
            func.coalesce(func.sum(case((Expense.is_fixed, Expense.amount), else_=0)), 0),
        ).where(Expense.date >= period.start, Expense.date <= period.end)
    ).one()
    return Figures(sales - refunds, cogs - cogs_back, opex, fixed)


def daily_figures(session: Session, period: Period) -> dict[date, Figures]:
    session.flush()
    start, end = period.utc_bounds()
    sales: dict[date, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # sales, cogs, opex, fixed
    for ts, total, cogs in session.execute(
        select(Sale.ts, Sale.total, Sale.cogs).where(Sale.ts >= start, Sale.ts < end)
    ):
        row = sales[_day(ts)]
        row[0] += total
        row[1] += cogs
    for ts, refund, cogs_back in session.execute(
        select(SaleReturn.ts, SaleReturn.refund_total, SaleReturn.cogs_reversed).where(
            SaleReturn.ts >= start, SaleReturn.ts < end
        )
    ):
        row = sales[_day(ts)]
        row[0] -= refund
        row[1] -= cogs_back
    for day, amount, is_fixed in session.execute(
        select(Expense.date, Expense.amount, Expense.is_fixed).where(
            Expense.date >= period.start, Expense.date <= period.end
        )
    ):
        row = sales[day]
        row[2] += amount
        row[3] += amount if is_fixed else 0
    return {d: Figures(*sales[d]) for d in period.dates()}


# Stock value and cash over time -----------------------------------------------------------------


def _movements(session: Session, before: datetime, product_ids: list[UUID] | None = None):
    stmt = (
        select(
            StockMovement.product_id,
            StockMovement.qty,
            StockMovement.wac_snapshot,
            StockMovement.ts,
        )
        .where(StockMovement.ts < before)
        .order_by(StockMovement.ts, StockMovement.id)
    )
    if product_ids is not None:
        stmt = stmt.where(StockMovement.product_id.in_(product_ids))
    return [m.Movement(pid, qty, wac, as_utc(ts)) for pid, qty, wac, ts in session.execute(stmt)]


def stock_value_by_day(session: Session, period: Period) -> dict[date, int]:
    """End-of-day stock value for each day in the period (today's is the current value)."""
    session.flush()
    boundaries = [m.day_start_utc(d + timedelta(days=1)) for d in period.dates()]
    values = m.stock_values(_movements(session, boundaries[-1]), boundaries)
    return dict(zip(period.dates(), values, strict=True))


def cash_by_day(session: Session, period: Period) -> dict[date, int]:
    """End-of-day balance across all accounts."""
    session.flush()
    rows = session.execute(
        select(CashLedger.ts, CashLedger.amount).where(
            CashLedger.ts < m.day_start_utc(period.end + timedelta(days=1))
        )
    ).all()
    totals: dict[date, int] = defaultdict(int)
    opening = 0
    for ts, amount in rows:
        day = _day(ts)
        if day < period.start:
            opening += amount
        else:
            totals[day] += amount
    out, running = {}, opening
    for d in period.dates():
        running += totals[d]
        out[d] = running
    return out


# Break-even -------------------------------------------------------------------------------------


def monthly_fixed_costs(session: Session, today: date) -> int:
    """Fixed costs for one month: active fixed recurring expenses (monthly equivalent) plus other
    fixed expenses from the last 30 days. Recurring postings are not counted twice, and new
    businesses get a figure from their schedules before any rent has been posted."""
    window = trailing(today)
    one_off = session.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.is_fixed,
            Expense.source != "recurring",
            Expense.date >= window.start,
            Expense.date <= window.end,
        )
    )
    schedules = session.execute(
        select(RecurringExpense.amount, RecurringExpense.frequency).where(
            RecurringExpense.active, RecurringExpense.is_fixed
        )
    )
    return one_off + sum(m.monthly_equivalent(amount, freq) for amount, freq in schedules)


def break_even(session: Session, business: Business, today: date | None = None) -> m.BreakEven:
    today = today or business_today()
    margin = figures(session, trailing(today)).gross_margin
    month_to_date = figures(session, Period(today.replace(day=1), today)).sales
    return m.break_even(
        monthly_fixed_costs=monthly_fixed_costs(session, today),
        gross_margin=margin,
        trading_days=business.trading_days_per_month,
        today=today,
        month_to_date_sales=month_to_date,
    )


# Dashboard --------------------------------------------------------------------------------------

METRICS = [
    "sales",
    "gross_margin",
    "operating_expenses",
    "net_profit",
    "stock_value",
    "cash_balance",
    "stock_turnover",
]


@dataclass(frozen=True)
class PeriodMetrics:
    period: Period
    values: dict[str, Decimal | int | None]


def _period_metrics(
    session: Session, period: Period, stock: dict[date, int], cash: dict[date, int]
) -> PeriodMetrics:
    f = figures(session, period)
    average_stock = m.average([stock[d] for d in period.dates()])
    return PeriodMetrics(
        period,
        {
            "sales": f.sales,
            "gross_margin": f.gross_margin,
            "operating_expenses": f.opex,
            "net_profit": f.net_profit,
            "stock_value": stock[period.end],
            "cash_balance": cash[period.end],
            "stock_turnover": m.turnover(f.cogs, average_stock),
        },
    )


def dashboard(
    session: Session, today: date | None = None
) -> dict[str, tuple[PeriodMetrics, PeriodMetrics]]:
    """The seven metrics for today, week and month, each with its comparison period."""
    today = today or business_today()
    periods = m.dashboard_periods(today)
    span = Period(min(p.start for pair in periods.values() for p in pair), today)
    stock = stock_value_by_day(session, span)
    cash = cash_by_day(session, span)
    return {
        name: (
            _period_metrics(session, current, stock, cash),
            _period_metrics(session, previous, stock, cash),
        )
        for name, (current, previous) in periods.items()
    }


# Daily history (metric_snapshots) ---------------------------------------------------------------


@dataclass(frozen=True)
class DayMetrics:
    date: date
    figures: Figures
    stock_value: int
    cash: int


def compute_days(session: Session, period: Period) -> list[DayMetrics]:
    daily = daily_figures(session, period)
    stock = stock_value_by_day(session, period)
    cash = cash_by_day(session, period)
    return [DayMetrics(d, daily[d], stock[d], cash[d]) for d in period.dates()]


def snapshot(session: Session, business: Business, period: Period) -> int:
    """Recompute and store finished days (upsert). Returns the number of days written."""
    existing = {
        s.date: s
        for s in session.scalars(
            select(MetricSnapshot).where(
                MetricSnapshot.date >= period.start, MetricSnapshot.date <= period.end
            )
        )
    }
    for day in compute_days(session, period):
        row = existing.get(day.date) or MetricSnapshot(business_id=business.id, date=day.date)
        row.sales = day.figures.sales
        row.cogs = day.figures.cogs
        row.gross_profit = day.figures.gross_profit
        row.opex = day.figures.opex
        row.net_profit = day.figures.net_profit
        row.stock_value = day.stock_value
        row.cash = day.cash
        row.computed_at = datetime.now(UTC)
        session.add(row)
    session.flush()
    return period.days


def daily_history(session: Session, days: int, today: date | None = None) -> list[DayMetrics]:
    """Finished days come from snapshots where present; today and any gaps are computed live."""
    today = today or business_today()
    period = trailing(today, days)
    stored = {
        s.date: DayMetrics(s.date, Figures(s.sales, s.cogs, s.opex, 0), s.stock_value, s.cash)
        for s in session.scalars(
            select(MetricSnapshot).where(
                MetricSnapshot.date >= period.start, MetricSnapshot.date < today
            )
        )
    }
    missing = [d for d in period.dates() if d not in stored]
    if missing:
        live = {day.date: day for day in compute_days(session, Period(min(missing), today))}
        stored.update({d: live[d] for d in missing})
    return [stored[d] for d in period.dates()]


# Product ranking --------------------------------------------------------------------------------


class RankBy(StrEnum):
    GROSS_PROFIT = "gross_profit"
    UNITS = "units"
    TURNOVER = "turnover"
    GMROI = "gmroi"


@dataclass(frozen=True)
class ProductRank:
    product: Product
    units: Decimal
    sales: int
    cogs: int
    average_stock_value: int
    turnover: Decimal | None
    gmroi: Decimal | None
    days_of_stock: Decimal | None

    @property
    def gross_profit(self) -> int:
        return self.sales - self.cogs


def product_ranking(session: Session, period: Period, rank_by: RankBy) -> list[ProductRank]:
    """Products by gross profit, units, turnover or GMROI (GP / average stock value)."""
    session.flush()
    start, end = period.utc_bounds()
    totals: dict[UUID, list] = defaultdict(lambda: [Decimal(0), 0, 0])  # units, sales, cogs
    for pid, qty, line_total, cogs in session.execute(
        select(SaleLine.product_id, SaleLine.qty, SaleLine.line_total, SaleLine.cogs)
        .join(Sale, Sale.id == SaleLine.sale_id)
        .where(Sale.ts >= start, Sale.ts < end)
    ):
        row = totals[pid]
        row[0] += qty
        row[1] += line_total
        row[2] += cogs
    for pid, qty, refund, cogs_back in session.execute(
        select(SaleLine.product_id, ReturnLine.qty, ReturnLine.refund, ReturnLine.cogs_reversed)
        .join(SaleLine, SaleLine.id == ReturnLine.sale_line_id)
        .join(SaleReturn, SaleReturn.id == ReturnLine.return_id)
        .where(SaleReturn.ts >= start, SaleReturn.ts < end)
    ):
        row = totals[pid]
        row[0] -= qty
        row[1] -= refund
        row[2] -= cogs_back

    products = list(session.scalars(select(Product).where(Product.active)))
    boundaries = [m.day_start_utc(d + timedelta(days=1)) for d in period.dates()]
    series = m.stock_values(_movements(session, boundaries[-1]), boundaries, per_product=True)
    ranks = []
    for product in products:
        units, sales, cogs = totals[product.id]
        avg_stock = m.average(series.get(product.id, []))
        ranks.append(
            ProductRank(
                product,
                units,
                sales,
                cogs,
                avg_stock,
                m.turnover(cogs, avg_stock),
                m.ratio(sales - cogs, avg_stock),
                m.days_of_stock(avg_stock, cogs, period.days),
            )
        )
    key = {
        RankBy.GROSS_PROFIT: lambda r: r.gross_profit,
        RankBy.UNITS: lambda r: r.units,
        RankBy.TURNOVER: lambda r: r.turnover if r.turnover is not None else Decimal(-1),
        RankBy.GMROI: lambda r: r.gmroi if r.gmroi is not None else Decimal(-(10**9)),
    }[rank_by]
    return sorted(ranks, key=lambda r: (key(r), r.product.name), reverse=True)
