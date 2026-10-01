"""Sets bought as one unit and sold as separate items (e.g. Sufuria sizes 1-5, a dinner set).

The set's cost is shared across its components in proportion to their selling prices (the
owner's decision), so every component earns the same margin."""

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

from app.domain.landed_cost import AllocationMethod, LineInput, allocate_shared_costs
from app.domain.money import Cents, to_cents


@dataclass(frozen=True)
class Component:
    qty: Decimal  # units of this component in one set
    price: Cents  # its selling price per unit


@dataclass(frozen=True)
class SetCostSplit:
    unit_costs: list[Cents]  # cost per unit of each component
    remainder: Cents  # cents left after rounding unit costs down (for all sets received)


def split_set_cost(components: list[Component], set_cost: Cents, sets: Decimal) -> SetCostSplit:
    """Share the cost of `sets` sets across the components by selling value (price x qty).

    Unit costs are rounded down to the cent and the remainder is returned, so the caller can book
    it and the recorded total stays exactly what was paid."""
    if any(c.price <= 0 for c in components):
        raise ValueError("every item in the set needs a selling price to share the cost")
    total = to_cents(Decimal(set_cost) * sets)
    shares = allocate_shared_costs(
        [LineInput(qty=c.qty * sets, bp=c.price) for c in components],
        total,
        AllocationMethod.BY_VALUE,
    )
    unit_costs = [
        int((Decimal(share) / (c.qty * sets)).to_integral_value(ROUND_FLOOR))
        for share, c in zip(shares, components, strict=True)
    ]
    booked = sum(to_cents(u * c.qty * sets) for u, c in zip(unit_costs, components, strict=True))
    return SetCostSplit(unit_costs, total - booked)
