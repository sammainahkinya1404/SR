"""Dashboard alerts (spec Part A §10).

Checks produce the set of conditions that hold right now; `sync` opens alerts for new ones,
refreshes the message on ones still active, and resolves the rest. Low stock is also re-checked
immediately through domain events when sales, returns or deliveries post (spec Part B §3); the
rest run in the daily job (`python -m app.jobs check-alerts`) or on demand.

The spec's "stock variance" alert waits for stock counts, which are not built yet."""

import datetime as dt
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import pricing
from app.domain.clock import business_today
from app.domain.inventory import MovementType
from app.domain.pricing import PricingMode
from app.domain.receipts import ksh
from app.models import Alert, Business, Product, SaleLine, StockMovement
from app.services import credit, events, metrics
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, NotFound
from app.services.products import qty_on_hand
from app.services.reports import profit_to_date


class AlertType(StrEnum):
    BELOW_BREAK_EVEN = "below_break_even"
    LOW_STOCK = "low_stock"
    SLOW_MOVING = "slow_moving"
    THIN_MARGIN = "thin_margin"
    LOW_CASH = "low_cash"
    CREDIT_RISK = "credit_risk"
    DRAWINGS = "drawings"


class AlertStatus(StrEnum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"  # seen by the owner; stays until the condition clears
    RESOLVED = "resolved"


ACTIVE = (AlertStatus.OPEN, AlertStatus.ACKNOWLEDGED)


@dataclass(frozen=True)
class Condition:
    type: AlertType
    entity_id: UUID | None
    message: str


# Checks -----------------------------------------------------------------------------------------


def _pct(x: Decimal) -> str:
    return f"{(x * 100).quantize(Decimal('0.1'))}%"


def low_stock(session: Session, product_ids: list[UUID] | None = None) -> list[Condition]:
    stmt = select(Product).where(Product.active, Product.reorder_point > 0)
    if product_ids is not None:
        stmt = stmt.where(Product.id.in_(product_ids))
    products = list(session.scalars(stmt))
    qty = qty_on_hand(session, [p.id for p in products])
    return [
        Condition(
            AlertType.LOW_STOCK,
            p.id,
            f"{p.name}: {qty[p.id]} {p.uom} left, at or below the reorder point of "
            f"{p.reorder_point}.",
        )
        for p in products
        if qty[p.id] <= p.reorder_point
    ]


def target_margin(product: Product, business: Business) -> Decimal:
    if product.pricing_mode == PricingMode.TARGET_MARGIN and product.target_value is not None:
        return product.target_value
    if product.pricing_mode == PricingMode.MARKUP and product.target_value is not None:
        return product.target_value / (1 + product.target_value)  # markup k = margin k/(1+k)
    return business.default_target_margin


def thin_margin(session: Session, business: Business) -> list[Condition]:
    found = []
    for p in session.scalars(select(Product).where(Product.active, Product.wac > 0)):
        margin = pricing.margin(p.price, p.wac)
        target = target_margin(p, business)
        if margin is not None and margin < target:
            found.append(
                Condition(
                    AlertType.THIN_MARGIN,
                    p.id,
                    f"{p.name}: margin {_pct(margin)} is below the {_pct(target)} target "
                    f"(price {ksh(p.price)}, cost {ksh(p.wac)}).",
                )
            )
    return found


def slow_moving(session: Session, business: Business, today: dt.date) -> list[Condition]:
    """No sale in N days (counted from the first delivery if never sold), or more than the
    maximum days of stock at the last 30 days' rate of sale."""
    products = {p.id: p for p in session.scalars(select(Product).where(Product.active))}
    qty = qty_on_hand(session, list(products))
    stocked = [pid for pid, q in qty.items() if q > 0]
    if not stocked:
        return []
    last_sale = dict(
        session.execute(
            select(StockMovement.product_id, func.max(StockMovement.ts))
            .where(StockMovement.type == MovementType.SALE, StockMovement.product_id.in_(stocked))
            .group_by(StockMovement.product_id)
        ).all()
    )
    first_in = dict(
        session.execute(
            select(StockMovement.product_id, func.min(StockMovement.ts))
            .where(StockMovement.qty > 0, StockMovement.product_id.in_(stocked))
            .group_by(StockMovement.product_id)
        ).all()
    )
    window = metrics.trailing(today)
    start, end = window.utc_bounds()
    sold = dict(
        session.execute(
            select(StockMovement.product_id, -func.sum(StockMovement.qty))
            .where(
                StockMovement.type.in_([MovementType.SALE, MovementType.RETURN]),
                StockMovement.product_id.in_(stocked),
                StockMovement.ts >= start,
                StockMovement.ts < end,
            )
            .group_by(StockMovement.product_id)
        ).all()
    )
    found = []
    for pid in stocked:
        product = products[pid]
        reference = last_sale.get(pid) or first_in.get(pid)
        idle = (today - business_today(metrics.as_utc(reference))).days if reference else 0
        if idle >= business.alert_slow_moving_days:
            reason = "no sale" if pid in last_sale else "never sold since delivery"
            found.append(
                Condition(
                    AlertType.SLOW_MOVING,
                    pid,
                    f"{product.name}: {reason} in {idle} days, {qty[pid]} {product.uom} on hand.",
                )
            )
            continue
        units = sold.get(pid) or Decimal(0)
        if units > 0:
            days = qty[pid] * window.days / units
            if days > business.alert_max_days_of_stock:
                found.append(
                    Condition(
                        AlertType.SLOW_MOVING,
                        pid,
                        f"{product.name}: {int(days)} days of stock at the current rate of sale "
                        f"(over {business.alert_max_days_of_stock}).",
                    )
                )
    return found


def business_checks(session: Session, business: Business, today: dt.date) -> list[Condition]:
    found = []
    be = metrics.break_even(session, business, today)
    if be.below:
        found.append(
            Condition(
                AlertType.BELOW_BREAK_EVEN,
                None,
                f"Month-to-date sales KSh {ksh(be.month_to_date_sales)} are under the "
                f"pro-rata break-even of KSh {ksh(be.pro_rata_target)}.",
            )
        )

    daily_fixed = Decimal(metrics.monthly_fixed_costs(session, today)) / 30
    cash_total = metrics.cash_by_day(session, metrics.Period(today, today))[today]
    floor = int(daily_fixed * business.alert_low_cash_days)
    if floor > 0 and cash_total < floor:
        found.append(
            Condition(
                AlertType.LOW_CASH,
                None,
                f"Cash across all accounts is KSh {ksh(cash_total)}, less than "
                f"{business.alert_low_cash_days} days of fixed costs (KSh {ksh(floor)}).",
            )
        )

    overdue = sum(i.outstanding for i in credit.open_invoices(session) if i.charge.due_date < today)
    recent_sales = metrics.figures(session, metrics.trailing(today)).sales
    limit = recent_sales * business.alert_credit_risk_pct
    if overdue > 0 and overdue > limit:
        found.append(
            Condition(
                AlertType.CREDIT_RISK,
                None,
                f"KSh {ksh(overdue)} of customer credit is overdue, more than "
                f"{_pct(business.alert_credit_risk_pct)} of the last 30 days' sales.",
            )
        )

    profit = profit_to_date(session)
    if profit.drawings > 0 and profit.drawings > profit.net_profit:
        found.append(
            Condition(
                AlertType.DRAWINGS,
                None,
                f"Drawings to date KSh {ksh(profit.drawings)} exceed net profit to date "
                f"KSh {ksh(profit.net_profit)}.",
            )
        )
    return found


# Sync -------------------------------------------------------------------------------------------


def sync(
    session: Session,
    business_id: UUID,
    found: list[Condition],
    types: set[AlertType],
    entity_ids: set[UUID] | None = None,
) -> tuple[int, int]:
    """Make the active alerts of `types` (optionally only these entities) match `found`.
    Returns (opened, resolved)."""
    now = datetime.now(UTC)
    stmt = select(Alert).where(Alert.type.in_(types), Alert.status.in_(ACTIVE))
    if entity_ids is not None:
        stmt = stmt.where(Alert.entity_id.in_(entity_ids))
    active = {(a.type, a.entity_id): a for a in session.scalars(stmt)}
    opened = 0
    for condition in found:
        alert = active.pop((condition.type, condition.entity_id), None)
        if alert is None:
            session.add(
                Alert(
                    business_id=business_id,
                    type=condition.type,
                    entity_id=condition.entity_id,
                    message=condition.message,
                    status=AlertStatus.OPEN,
                )
            )
            opened += 1
        elif alert.message != condition.message:
            alert.message = condition.message
            alert.updated_at = now
    for alert in active.values():  # conditions that no longer hold
        alert.status = AlertStatus.RESOLVED
        alert.resolved_at = now
        alert.updated_at = now
    session.flush()
    return opened, len(active)


def run_checks(
    session: Session, business: Business, today: dt.date | None = None
) -> tuple[int, int]:
    today = today or business_today()
    found = (
        low_stock(session)
        + thin_margin(session, business)
        + slow_moving(session, business, today)
        + business_checks(session, business, today)
    )
    return sync(session, business.id, found, set(AlertType))


def refresh_low_stock(session: Session, business_id: UUID, product_ids: list[UUID]) -> None:
    ids = set(product_ids)
    sync(session, business_id, low_stock(session, list(ids)), {AlertType.LOW_STOCK}, ids)


# Event handlers ---------------------------------------------------------------------------------


def _on_sale(session: Session, event: events.SalePosted | events.SaleReturned) -> None:
    product_ids = session.scalars(
        select(SaleLine.product_id).where(SaleLine.sale_id == event.sale_id)
    ).all()
    refresh_low_stock(session, event.business_id, list(product_ids))


def _on_stock_received(session: Session, event: events.StockReceived) -> None:
    refresh_low_stock(session, event.business_id, list(event.product_ids))


_registered = False


def register() -> None:
    """Subscribe the real-time checks to domain events (idempotent)."""
    global _registered
    if _registered:
        return
    events.subscribe(events.SalePosted, _on_sale)
    events.subscribe(events.SaleReturned, _on_sale)
    events.subscribe(events.StockReceived, _on_stock_received)
    _registered = True


# Queries ----------------------------------------------------------------------------------------


def list_alerts(session: Session, include_resolved: bool) -> list[Alert]:
    stmt = select(Alert).order_by(Alert.created_at.desc())
    if not include_resolved:
        stmt = stmt.where(Alert.status.in_(ACTIVE))
    return list(session.scalars(stmt))


def acknowledge(session: Session, actor: Actor, alert_id: UUID) -> Alert:
    require_owner(actor, "acknowledge alerts")
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise NotFound("alert not found")
    if alert.status != AlertStatus.OPEN:
        raise Conflict(f"alert is {alert.status}")
    alert.status = AlertStatus.ACKNOWLEDGED
    alert.updated_at = datetime.now(UTC)
    return alert
