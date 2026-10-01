"""Dashboard, reports, alerts and business settings. Owner-only."""

import datetime as dt
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import Ctx
from app.api.exports import Format, ksh, table
from app.domain.clock import business_today
from app.domain.metrics import Period, change_pct
from app.schemas.businesses import SettingsOut, SettingsUpdate
from app.schemas.reports import (
    AlertOut,
    AlertRunOut,
    BreakEvenOut,
    DashboardOut,
    DayOut,
    MetricValue,
    PeriodOut,
    ProductRankOut,
    ProfitReportOut,
    ProfitTotals,
)
from app.services import alerts, businesses, metrics
from app.services.actor import require_owner
from app.services.errors import RuleViolation
from app.services.metrics import RankBy

router = APIRouter(tags=["reports"])

MAX_REPORT_DAYS = 366


def _period(since: dt.date | None, until: dt.date | None, default_days: int = 30) -> Period:
    until = until or business_today()
    since = since or until - dt.timedelta(days=default_days - 1)
    if since > until:
        raise RuleViolation("since must be on or before until")
    if (until - since).days >= MAX_REPORT_DAYS:
        raise RuleViolation(f"reports cover at most {MAX_REPORT_DAYS} days")
    return Period(since, until)


def _break_even_out(be) -> BreakEvenOut:
    return BreakEvenOut(
        monthly_fixed_costs=be.monthly_fixed_costs,
        gross_margin=be.gross_margin,
        monthly=be.monthly,
        daily=be.daily,
        month_to_date_sales=be.month_to_date_sales,
        pro_rata_target=be.pro_rata_target,
        below=be.below,
    )


def _day_out(day: metrics.DayMetrics) -> DayOut:
    f = day.figures
    return DayOut(
        date=day.date,
        sales=f.sales,
        cogs=f.cogs,
        gross_profit=f.gross_profit,
        opex=f.opex,
        net_profit=f.net_profit,
        stock_value=day.stock_value,
        cash=day.cash,
    )


DAY_HEADERS = ["date", "sales_ksh", "cogs_ksh", "gross_profit_ksh", "expenses_ksh",
               "net_profit_ksh", "stock_value_ksh", "cash_ksh"]  # fmt: skip


def _day_row(d: DayOut) -> list:
    return [d.date.isoformat(), ksh(d.sales), ksh(d.cogs), ksh(d.gross_profit), ksh(d.opex),
            ksh(d.net_profit), ksh(d.stock_value), ksh(d.cash)]  # fmt: skip


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(ctx: Ctx):
    """The seven metrics for today, this week and this month, each against the same span of the
    previous period, plus break-even and the active alerts."""
    require_owner(ctx.actor, "view the dashboard")
    today = business_today()
    periods = {}
    for name, (current, previous) in metrics.dashboard(ctx.session, today).items():
        periods[name] = PeriodOut(
            start=current.period.start,
            end=current.period.end,
            compared_to_start=previous.period.start,
            compared_to_end=previous.period.end,
            metrics={
                key: MetricValue(
                    value=current.values[key],
                    previous=previous.values[key],
                    change=change_pct(current.values[key], previous.values[key]),
                )
                for key in metrics.METRICS
            },
        )
    return DashboardOut(
        as_of=today,
        periods=periods,
        break_even=_break_even_out(metrics.break_even(ctx.session, ctx.business, today)),
        alerts=[AlertOut.model_validate(a) for a in alerts.list_alerts(ctx.session, False)],
    )


@router.get("/metrics/daily", response_model=list[DayOut])
def daily_metrics(
    ctx: Ctx, days: int = Query(default=30, ge=1, le=MAX_REPORT_DAYS), format: Format = Format.JSON
):
    require_owner(ctx.actor, "view metrics")
    rows = [_day_out(d) for d in metrics.daily_history(ctx.session, days)]
    if format is Format.JSON:
        return rows
    return table(format, "daily-metrics", DAY_HEADERS, [_day_row(d) for d in rows])


@router.get("/reports/profit", response_model=ProfitReportOut)
def profit_report(
    ctx: Ctx,
    since: dt.date | None = None,
    until: dt.date | None = None,
    format: Format = Format.JSON,
):
    """Net profit = gross profit - operating expenses, by day (spec Part A §9)."""
    require_owner(ctx.actor, "view profit reports")
    period = _period(since, until)
    days = [_day_out(d) for d in metrics.compute_days(ctx.session, period)]
    if format is not Format.JSON:
        return table(format, "profit", DAY_HEADERS, [_day_row(d) for d in days])
    f = metrics.figures(ctx.session, period)
    return ProfitReportOut(
        since=period.start,
        until=period.end,
        totals=ProfitTotals(
            sales=f.sales,
            cogs=f.cogs,
            gross_profit=f.gross_profit,
            gross_margin=f.gross_margin,
            operating_expenses=f.opex,
            fixed_expenses=f.fixed_opex,
            net_profit=f.net_profit,
        ),
        days=days,
    )


@router.get("/reports/break-even", response_model=BreakEvenOut)
def break_even(ctx: Ctx):
    require_owner(ctx.actor, "view break-even")
    return _break_even_out(metrics.break_even(ctx.session, ctx.business))


@router.get("/reports/products", response_model=list[ProductRankOut])
def product_ranking(
    ctx: Ctx,
    since: dt.date | None = None,
    until: dt.date | None = None,
    sort: RankBy = RankBy.GROSS_PROFIT,
    format: Format = Format.JSON,
):
    """Products ranked by gross profit, units sold, turnover or GMROI (spec Part A §9)."""
    require_owner(ctx.actor, "view product rankings")
    ranks = metrics.product_ranking(ctx.session, _period(since, until), sort)
    rows = [
        ProductRankOut(
            product_id=r.product.id,
            sku=r.product.sku,
            name=r.product.name,
            units_sold=r.units,
            sales=r.sales,
            cogs=r.cogs,
            gross_profit=r.gross_profit,
            average_stock_value=r.average_stock_value,
            turnover=r.turnover,
            gmroi=r.gmroi,
            days_of_stock=r.days_of_stock,
        )
        for r in ranks
    ]
    if format is Format.JSON:
        return rows
    headers = ["sku", "name", "units_sold", "sales_ksh", "cogs_ksh", "gross_profit_ksh",
               "average_stock_value_ksh", "turnover", "gmroi", "days_of_stock"]  # fmt: skip
    return table(
        format,
        f"products-by-{sort}",
        headers,
        [
            [
                r.sku,
                r.name,
                r.units_sold,
                ksh(r.sales),
                ksh(r.cogs),
                ksh(r.gross_profit),
                ksh(r.average_stock_value),
                r.turnover,
                r.gmroi,
                r.days_of_stock,
            ]  # fmt: skip
            for r in rows
        ],
    )


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(ctx: Ctx, include_resolved: bool = False):
    require_owner(ctx.actor, "view alerts")
    return alerts.list_alerts(ctx.session, include_resolved)


@router.post("/alerts/run", response_model=AlertRunOut)
def run_alerts(ctx: Ctx):
    """Run every check now. The daily job (`python -m app.jobs check-alerts`) does the same."""
    require_owner(ctx.actor, "run alert checks")
    opened, resolved = alerts.run_checks(ctx.session, ctx.business)
    active = alerts.list_alerts(ctx.session, False)
    return AlertRunOut(opened=opened, resolved=resolved, active=active)


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(alert_id: UUID, ctx: Ctx):
    return alerts.acknowledge(ctx.session, ctx.actor, alert_id)


@router.get("/settings", response_model=SettingsOut)
def get_settings(ctx: Ctx):
    require_owner(ctx.actor, "view business settings")
    return businesses.settings_out(ctx.business)


@router.patch("/settings", response_model=SettingsOut)
def update_settings(data: SettingsUpdate, ctx: Ctx):
    return businesses.settings_out(
        businesses.update_settings(ctx.session, ctx.actor, ctx.business, data)
    )
