"""Spec Part A §2: weighted average cost."""

from decimal import Decimal
from enum import StrEnum

from app.domain.money import Cents, to_cents


class MovementType(StrEnum):
    PURCHASE = "purchase"
    SALE = "sale"
    RETURN = "return"
    ADJUSTMENT = "adjustment"
    DAMAGE = "damage"
    THEFT = "theft"
    OWNER_CONSUMPTION = "owner_consumption"


def new_wac(old_qty: Decimal, old_wac: Cents, in_qty: Decimal, landed_cost: Cents) -> Cents:
    """new WAC = (old qty x old WAC + in qty x landed cost) / (old qty + in qty)

    When there is no stock on hand (or it is negative after offline sales) the old WAC carries no
    information about the goods now on the shelf, so the incoming landed cost becomes the WAC.
    """
    if old_qty <= 0:
        return landed_cost
    return to_cents((old_qty * old_wac + in_qty * landed_cost) / (old_qty + in_qty))


def stock_value(qty: Decimal, wac: Cents) -> Cents:
    return to_cents(qty * wac)
