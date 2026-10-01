from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

Cents = int


def to_cents(amount: Decimal, rounding: str = ROUND_HALF_UP) -> Cents:
    """Round a Decimal amount already expressed in cents to a whole cent."""
    return int(amount.quantize(Decimal(1), rounding=rounding))


def to_cents_ceiling(amount: Decimal) -> Cents:
    return to_cents(amount, ROUND_CEILING)
