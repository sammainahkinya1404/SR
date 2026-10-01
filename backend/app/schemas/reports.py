import datetime as dt
from decimal import Decimal
from uuid import UUID

from app.schemas.common import Schema


class MetricValue(Schema):
    value: Decimal | int | None  # cents, or a fraction for margin/turnover (None = undefined)
    previous: Decimal | int | None
    change: Decimal | None  # relative change vs previous (0.12 = +12%)


class PeriodOut(Schema):
    start: dt.date
    end: dt.date
    compared_to_start: dt.date
    compared_to_end: dt.date
    metrics: dict[str, MetricValue]


class BreakEvenOut(Schema):
    monthly_fixed_costs: int
    gross_margin: Decimal | None  # trailing 30 days
    monthly: int | None  # None when there is no positive margin yet
    daily: int | None
    month_to_date_sales: int
    pro_rata_target: int | None
    below: bool


class AlertOut(Schema):
    id: UUID
    type: str
    entity_id: UUID | None
    message: str
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime
    resolved_at: dt.datetime | None


class DashboardOut(Schema):
    as_of: dt.date
    periods: dict[str, PeriodOut]  # today, week, month
    break_even: BreakEvenOut
    alerts: list[AlertOut]


class DayOut(Schema):
    date: dt.date
    sales: int
    cogs: int
    gross_profit: int
    opex: int
    net_profit: int
    stock_value: int
    cash: int


class ProfitTotals(Schema):
    sales: int
    cogs: int
    gross_profit: int
    gross_margin: Decimal | None
    operating_expenses: int
    fixed_expenses: int
    net_profit: int


class ProfitReportOut(Schema):
    since: dt.date
    until: dt.date
    totals: ProfitTotals
    days: list[DayOut]


class ProductRankOut(Schema):
    product_id: UUID
    sku: str
    name: str
    units_sold: Decimal
    sales: int
    cogs: int
    gross_profit: int
    average_stock_value: int
    turnover: Decimal | None
    gmroi: Decimal | None
    days_of_stock: Decimal | None


class AlertRunOut(Schema):
    opened: int
    resolved: int
    active: list[AlertOut]
