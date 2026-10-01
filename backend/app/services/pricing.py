from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain import pricing as rules
from app.models import Business, PriceHistory, PriceSuggestion, Product
from app.services import audit, events
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, NotFound, RuleViolation


class SuggestionStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


def change_price(
    session: Session, actor: Actor, product: Product, new_price: int, reason: str
) -> None:
    """The only way a product's price changes: writes price history, audit and PriceChanged."""
    old_price = product.price
    if new_price == old_price:
        return
    session.add(
        PriceHistory(
            business_id=actor.business_id,
            product_id=product.id,
            old_price=old_price,
            new_price=new_price,
            reason=reason,
            user_id=actor.user_id,
        )
    )
    audit.record(session, actor, "product", product.id, "price", old_price, new_price)
    product.price = new_price
    # Keep the price range valid: a minimum above the selling price comes down with it.
    if product.min_price is not None and product.min_price > new_price:
        audit.record(
            session, actor, "product", product.id, "min_price", product.min_price, new_price
        )
        product.min_price = new_price
    events.publish(
        session, events.PriceChanged(actor.business_id, product.id, old_price, new_price)
    )


def set_pricing(
    session: Session,
    actor: Actor,
    business: Business,
    product: Product,
    mode: rules.PricingMode,
    target: Decimal | None,
    manual_price: int | None,
    reason: str,
) -> None:
    require_owner(actor, "change prices")
    if mode is rules.PricingMode.MANUAL:
        if manual_price is None:
            raise RuleViolation("manual pricing needs price_cents")
        target = None
        new_price = manual_price
    else:
        if target is None:
            raise RuleViolation(f"{mode} pricing needs target_value")
        try:
            raw = rules.price_from_cost(mode, product.wac, target)
        except ValueError as e:
            raise RuleViolation(str(e)) from e
        # With no cost yet the rule cannot price; the first stock-in will raise a suggestion.
        new_price = (
            rules.round_to_increment(raw, business.price_rounding) if product.wac else product.price
        )

    if (mode, target) != (product.pricing_mode, product.target_value):
        audit.record(
            session, actor, "product", product.id, "pricing_mode", product.pricing_mode, mode
        )
        audit.record(
            session, actor, "product", product.id, "target_value", product.target_value, target
        )
        product.pricing_mode = mode
        product.target_value = target
    change_price(session, actor, product, new_price, reason)


def set_min_prices(
    session: Session, actor: Actor, items: list[tuple[UUID, int | None]]
) -> list[Product]:
    """Set (or clear) the bottom of each item's price range. Owner only; every change audited."""
    require_owner(actor, "set minimum prices")
    changed = []
    for product_id, min_price in items:
        product = session.get(Product, product_id, with_for_update=True)
        if product is None:
            raise NotFound(f"product {product_id} not found")
        if min_price is not None:
            if product.price <= 0:
                raise RuleViolation(f"{product.name}: set a selling price before a minimum")
            if min_price > product.price:
                raise RuleViolation(
                    f"{product.name}: the minimum can't be above the selling price "
                    f"({product.price / 100:.2f})"
                )
        if product.min_price != min_price:
            audit.record(
                session, actor, "product", product.id, "min_price", product.min_price, min_price
            )
            product.min_price = min_price
        changed.append(product)
    return changed


def propose_reprice(
    session: Session, business: Business, product: Product, old_wac: int
) -> PriceSuggestion | None:
    """After a WAC change beyond the threshold, queue a suggested price for the owner.

    Any older pending suggestion for the product is superseded so the owner only sees one."""
    if not rules.wac_change_exceeds(old_wac, product.wac, business.reprice_threshold_pct):
        return None
    suggested = rules.suggest_price(
        mode=rules.PricingMode(product.pricing_mode),
        target=product.target_value,
        new_wac=product.wac,
        old_wac=old_wac,
        current_price=product.price,
        increment=business.price_rounding,
    )
    if suggested is None or suggested == product.price:
        return None
    session.execute(
        update(PriceSuggestion)
        .where(
            PriceSuggestion.product_id == product.id,
            PriceSuggestion.status == SuggestionStatus.PENDING,
        )
        .values(status=SuggestionStatus.SUPERSEDED)
    )
    suggestion = PriceSuggestion(
        business_id=business.id,
        product_id=product.id,
        suggested_price=suggested,
        price_at_suggestion=product.price,
        previous_wac=old_wac,
        trigger_wac=product.wac,
        status=SuggestionStatus.PENDING,
    )
    session.add(suggestion)
    return suggestion


def list_suggestions(session: Session, status: SuggestionStatus | None) -> list[PriceSuggestion]:
    stmt = select(PriceSuggestion).order_by(PriceSuggestion.created_at)
    if status is not None:
        stmt = stmt.where(PriceSuggestion.status == status)
    return list(session.scalars(stmt))


def decide_suggestion(
    session: Session, actor: Actor, suggestion_id: UUID, approve: bool
) -> PriceSuggestion:
    require_owner(actor, "decide price suggestions")
    suggestion = session.get(PriceSuggestion, suggestion_id, with_for_update=True)
    if suggestion is None:
        raise NotFound("price suggestion not found")
    if suggestion.status != SuggestionStatus.PENDING:
        raise Conflict(f"suggestion is already {suggestion.status}")
    if approve:
        return apply_suggestion(
            session,
            actor,
            suggestion,
            f"approved price suggestion {suggestion.id} (WAC {suggestion.previous_wac}"
            f" -> {suggestion.trigger_wac})",
        )
    suggestion.status = SuggestionStatus.REJECTED
    suggestion.decided_by = actor.user_id
    suggestion.decided_at = datetime.now(UTC)
    return suggestion


def apply_suggestion(
    session: Session, actor: Actor, suggestion: PriceSuggestion, reason: str
) -> PriceSuggestion:
    product = session.get(Product, suggestion.product_id, with_for_update=True)
    assert product is not None
    change_price(session, actor, product, suggestion.suggested_price, reason)
    suggestion.status = SuggestionStatus.APPROVED
    suggestion.decided_by = actor.user_id
    suggestion.decided_at = datetime.now(UTC)
    return suggestion
