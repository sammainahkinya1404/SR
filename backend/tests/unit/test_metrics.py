import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from app.domain.metrics import (
    Figures,
    Movement,
    Period,
    break_even,
    change_pct,
    dashboard_periods,
    days_of_stock,
    monthly_equivalent,
    stock_values,
    turnover,
)


def test_dashboard_periods_compare_like_for_like():
    p = dashboard_periods(date(2026, 9, 29))  # a Tuesday
    assert p["today"] == (
        Period(date(2026, 9, 29), date(2026, 9, 29)),
        Period(date(2026, 9, 28), date(2026, 9, 28)),
    )
    assert p["week"] == (
        Period(date(2026, 9, 28), date(2026, 9, 29)),
        Period(date(2026, 9, 21), date(2026, 9, 22)),
    )
    assert p["month"] == (
        Period(date(2026, 9, 1), date(2026, 9, 29)),
        Period(date(2026, 8, 1), date(2026, 8, 29)),
    )


def test_month_comparison_is_clamped_to_a_shorter_previous_month():
    current, previous = dashboard_periods(date(2026, 3, 31))["month"]
    assert previous == Period(date(2026, 2, 1), date(2026, 2, 28))


def test_business_days_map_to_utc_ranges():
    start, end = Period(date(2026, 9, 29), date(2026, 9, 29)).utc_bounds()
    assert (start, end) == (
        datetime(2026, 9, 28, 21, tzinfo=UTC),
        datetime(2026, 9, 29, 21, tzinfo=UTC),
    )


def test_figures():
    f = Figures(sales=30_000, cogs=20_000, opex=5_000, fixed_opex=0)
    assert (f.gross_profit, f.net_profit) == (10_000, 5_000)
    assert f.gross_margin == Decimal(1) / 3
    assert Figures(0, 0, 100, 0).gross_margin is None


def test_break_even():
    be = break_even(
        monthly_fixed_costs=520_000,
        gross_margin=Decimal("0.25"),
        trading_days=26,
        today=date(2026, 9, 15),
        month_to_date_sales=1_000_000,
    )
    assert (be.monthly, be.daily) == (2_080_000, 80_000)
    assert be.pro_rata_target == 1_040_000  # 15 of 30 days
    assert be.below


def test_break_even_is_undefined_without_a_positive_margin():
    be = break_even(
        monthly_fixed_costs=1,
        gross_margin=None,
        trading_days=26,
        today=date(2026, 9, 15),
        month_to_date_sales=0,
    )
    assert (be.monthly, be.pro_rata_target, be.below) == (None, None, False)


def test_weekly_costs_as_monthly():
    assert monthly_equivalent(12_000, "weekly") == 52_000
    assert monthly_equivalent(12_000, "monthly") == 12_000


def at(hour: int) -> datetime:
    return datetime(2026, 9, 29, hour, tzinfo=UTC)


def test_stock_value_is_replayed_from_the_ledger():
    rice, sugar = uuid.uuid4(), uuid.uuid4()
    movements = [
        Movement(rice, Decimal(10), 100, at(1)),  # 10 @ 100
        Movement(rice, Decimal(-2), 100, at(3)),  # sale
        Movement(sugar, Decimal(5), 50, at(5)),
        Movement(rice, Decimal(10), 110, at(7)),  # delivery moves WAC to 110
    ]
    assert stock_values(movements, [at(0), at(2), at(4), at(6), at(8)]) == [
        0,
        1_000,
        800,
        1_050,
        2_230,
    ]
    per_product = stock_values(movements, [at(2), at(6)], per_product=True)
    assert per_product == {rice: [1_000, 800], sugar: [0, 250]}


def test_turnover_and_days_of_stock():
    assert turnover(20_000, 80_000) == Decimal("0.25")
    assert turnover(20_000, 0) is None
    # 80,000 of stock against 20,000 of COGS over 30 days = 120 days of stock.
    assert days_of_stock(80_000, 20_000, 30) == 120
    assert days_of_stock(80_000, 0, 30) is None


def test_change_pct():
    assert change_pct(12, 10) == Decimal("0.2")
    assert change_pct(-5, -10) == Decimal("0.5")
    assert change_pct(5, 0) is None
    assert change_pct(None, 5) is None
