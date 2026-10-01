"""Spec Part A §4: pricing engine."""

from decimal import Decimal
from enum import StrEnum

from app.domain.money import Cents, to_cents_ceiling


class PricingMode(StrEnum):
    TARGET_MARGIN = "target_margin"
    MARKUP = "markup"
    MANUAL = "manual"


def round_to_increment(amount: Decimal, increment: Cents) -> Cents:
    """Round up to the next increment (e.g. 500 cents = KSh 5), so rounding never takes a price
    below what the pricing rule asks for (owner's decision; the spec suggested nearest)."""
    if increment <= 1:
        return to_cents_ceiling(amount)
    return to_cents_ceiling(amount / increment) * increment


def price_from_cost(mode: PricingMode, cost: Cents, target: Decimal) -> Decimal:
    """Unrounded price for a rule-based mode. `target` is a fraction (0.25 = 25%)."""
    if mode is PricingMode.TARGET_MARGIN:
        if not 0 <= target < 1:
            raise ValueError("target margin must be in [0, 1)")
        return Decimal(cost) / (1 - target)
    if mode is PricingMode.MARKUP:
        if target < 0:
            raise ValueError("markup must be >= 0")
        return Decimal(cost) * (1 + target)
    raise ValueError("manual pricing has no formula")


def margin(price: Cents, cost: Cents) -> Decimal | None:
    """(P - C) / P, or None when price is zero."""
    return None if price == 0 else Decimal(price - cost) / price


def markup(price: Cents, cost: Cents) -> Decimal | None:
    """(P - C) / C, or None when cost is zero."""
    return None if cost == 0 else Decimal(price - cost) / cost


def floor_price(wac: Cents, floor_pct: Decimal) -> Cents:
    """Automatic minimum selling price, rounded up so the floor is never undercut by rounding."""
    return to_cents_ceiling(wac * (1 + floor_pct))


def effective_floor(min_price: Cents | None, wac: Cents, floor_pct: Decimal) -> Cents:
    """The lowest price an item may be sold at without the owner: its own minimum when the owner
    has set one (the bottom of its price range), otherwise the automatic cost + floor %."""
    return min_price if min_price is not None else floor_price(wac, floor_pct)


def wac_change_exceeds(old_wac: Cents, new_wac: Cents, threshold: Decimal) -> bool:
    """True when WAC moved by more than `threshold` (a fraction). A first cost counts."""
    if old_wac == 0:
        return new_wac != 0
    return abs(Decimal(new_wac - old_wac)) / old_wac > threshold


def suggest_price(
    *,
    mode: PricingMode,
    target: Decimal | None,
    new_wac: Cents,
    old_wac: Cents,
    current_price: Cents,
    increment: Cents,
) -> Cents | None:
    """Price to propose after a WAC change, or None if there is no sensible suggestion.

    Rule-based modes re-apply their rule to the new WAC. Manual prices keep the margin the product
    had at the old WAC.
    """
    if mode is not PricingMode.MANUAL and target is not None:
        return round_to_increment(price_from_cost(mode, new_wac, target), increment)
    current_margin = margin(current_price, old_wac) if old_wac > 0 else None
    if current_margin is None or current_margin >= 1:
        return None
    return round_to_increment(Decimal(new_wac) / (1 - current_margin), increment)
