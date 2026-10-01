"""Spec Part A §3: allocating shared stock-in costs across batch lines."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.domain.money import Cents, to_cents


class AllocationMethod(StrEnum):
    BY_VALUE = "by_value"
    BY_QUANTITY = "by_quantity"


class SharedCostType(StrEnum):
    TRANSPORT = "transport"
    DUTY = "duty"
    PACKAGING = "packaging"
    OTHER = "other"


@dataclass(frozen=True)
class LineInput:
    qty: Decimal
    bp: Cents  # buying price per unit


def missing_cost_types(entered: set[str]) -> list[SharedCostType]:
    """Cost types neither entered nor explicitly zeroed. Posting is blocked until this is empty."""
    return [t for t in SharedCostType if t.value not in entered]


def allocate_shared_costs(
    lines: list[LineInput], shared_total: Cents, method: AllocationMethod
) -> list[Cents]:
    """Split `shared_total` across lines by largest remainder, so the parts sum exactly.

    By value weights each line by BP x qty; by quantity weights by qty. If every value weight is
    zero (e.g. a batch of free samples) it falls back to quantity.
    """
    if not lines:
        return []
    if method is AllocationMethod.BY_VALUE:
        weights = [line.bp * line.qty for line in lines]
        if sum(weights) == 0:
            weights = [line.qty for line in lines]
    else:
        weights = [line.qty for line in lines]

    total_weight = sum(weights)
    if total_weight == 0 or shared_total == 0:
        return [0] * len(lines)

    exact = [Decimal(shared_total) * w / total_weight for w in weights]
    floors = [int(e) for e in exact]  # weights and total are non-negative, so int() floors
    leftover = shared_total - sum(floors)
    # Hand the remaining cents to the largest fractional parts; ties go to the earlier line.
    order = sorted(range(len(lines)), key=lambda i: (-(exact[i] - floors[i]), i))
    for i in order[:leftover]:
        floors[i] += 1
    return floors


def landed_unit_cost(qty: Decimal, bp: Cents, allocated: Cents) -> Cents:
    """landed unit cost = (BP x qty + allocated shared costs) / qty"""
    return to_cents((bp * qty + allocated) / qty)
