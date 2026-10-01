"""Adding stock in one step (single item or bulk order), built on the stock-in batch flow.

Items are given by name; unknown names become new products, and a set's name stocks each of its
components (the set's cost shared by selling price, see domain/sets.py). The one transport payment
is shared across the lines (by value or quantity) to get each item's landed cost, then the batch is
posted: stock movements, weighted average cost, and the pricing engine."""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.clock import business_today
from app.domain.landed_cost import SharedCostType
from app.domain.money import to_cents
from app.domain.pricing import PricingMode
from app.domain.sets import Component, split_set_cost
from app.models import Business, PriceSuggestion, Product, StockInBatch
from app.schemas.inventory import ReceiveCreate, ReceivedLine, ReceiveOut
from app.schemas.products import ProductCreate
from app.schemas.stock_in import BatchCreate, LineIn
from app.services import products, sets, stock_in
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, RuleViolation
from app.services.pricing import SuggestionStatus, apply_suggestion


@dataclass
class _Line:
    product: Product
    qty: Decimal
    bp: int
    is_new: bool
    set_name: str | None = None


def receive(session: Session, actor: Actor, business: Business, data: ReceiveCreate) -> ReceiveOut:
    require_owner(actor, "add stock")
    if session.get(StockInBatch, data.id) is not None:
        raise Conflict("this delivery was already recorded")

    # Resolve each item to batch lines: a product (created by name if new), or a set expanded into
    # its components. Rounding cents from splitting set costs are booked as "other" shared cost,
    # so the delivery's total is exactly what was paid.
    lines: list[_Line] = []
    created: dict[str, Product] = {}
    rounding = 0
    goods_value = 0
    for item in data.items:
        product_set = None
        if item.set_id is not None:
            product_set = sets.get_set(session, item.set_id)
        elif item.product_id is None:
            product_set = sets.find_set_by_name(session, item.name)
        if product_set is not None:
            components = product_set.components
            if not components:
                raise RuleViolation(f"the set {product_set.name!r} has no items")
            members = {
                p.id: p
                for p in session.scalars(
                    select(Product).where(Product.id.in_([c.product_id for c in components]))
                )
            }
            try:
                split = split_set_cost(
                    [Component(c.qty, members[c.product_id].price) for c in components],
                    item.bp_cents,
                    item.qty,
                )
            except ValueError as e:
                raise RuleViolation(f"{product_set.name}: {e}") from e
            rounding += split.remainder
            goods_value += to_cents(item.qty * item.bp_cents)
            for c, unit_cost in zip(components, split.unit_costs, strict=True):
                lines.append(
                    _Line(
                        members[c.product_id], c.qty * item.qty, unit_cost, False, product_set.name
                    )
                )
            continue
        goods_value += to_cents(item.qty * item.bp_cents)
        if item.product_id is not None:
            product = products.get_product(session, item.product_id)
            lines.append(_Line(product, item.qty, item.bp_cents, False))
            continue
        key = item.name.strip().lower()
        if key in created:
            lines.append(_Line(created[key], item.qty, item.bp_cents, True))
        elif (existing := products.find_by_name(session, item.name)) is not None:
            lines.append(_Line(existing, item.qty, item.bp_cents, False))
        else:
            # New items are priced by the pricing engine at the shop's default target margin.
            product = products.create_product(
                session,
                actor,
                ProductCreate(
                    name=item.name,
                    category=(item.category or "").strip() or None,
                    pricing_mode=PricingMode.TARGET_MARGIN,
                    target_value=business.default_target_margin,
                ),
            )
            created[key] = product
            lines.append(_Line(product, item.qty, item.bp_cents, True))

    batch = stock_in.create_batch(
        session,
        actor,
        business,
        BatchCreate(
            id=data.id,
            date=data.date or business_today(),
            allocation_method=data.allocation_method,
            lines=[LineIn(product_id=ln.product.id, qty=ln.qty, bp_cents=ln.bp) for ln in lines],
            # Only transport is asked for; "other" carries set-split rounding; the rest are zero.
            costs={
                SharedCostType.TRANSPORT: data.transport_cents,
                SharedCostType.DUTY: 0,
                SharedCostType.PACKAGING: 0,
                SharedCostType.OTHER: rounding,
            },
        ),
    )
    stock_in.post_batch(session, actor, business, batch.id)

    # A product with no price yet (new, or never priced) takes the engine's price straight away:
    # there is no existing price to protect. Otherwise the suggestion waits for the owner.
    price_status: dict = {}
    for product in (ln.product for ln in lines):
        if product.id in price_status:
            continue
        suggestion = session.scalar(
            select(PriceSuggestion).where(
                PriceSuggestion.product_id == product.id,
                PriceSuggestion.status == SuggestionStatus.PENDING,
            )
        )
        if suggestion is not None and product.price == 0:
            apply_suggestion(session, actor, suggestion, "initial price from the pricing rule")
            price_status[product.id] = "set"
        elif suggestion is not None:
            price_status[product.id] = "suggested"
        else:
            price_status[product.id] = "unchanged"

    session.flush()
    received = []
    for line, ln in zip(batch.lines, lines, strict=True):
        product = ln.product
        received.append(
            ReceivedLine(
                product_id=product.id,
                name=product.name,
                set_name=ln.set_name,
                category=product.category,
                new_product=ln.is_new,
                qty=line.qty,
                bp_cents=line.bp,
                transport_share_cents=line.allocated_cost,
                landed_unit_cost_cents=line.landed_unit_cost,
                wac_cents=product.wac,
                price_cents=product.price,
                price_status=price_status[product.id],
            )
        )
    return ReceiveOut(
        id=batch.id,
        date=batch.date,
        allocation_method=data.allocation_method,
        goods_value_cents=goods_value,
        transport_cents=data.transport_cents,
        lines=received,
    )
