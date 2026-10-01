from decimal import Decimal

from sqlalchemy import BigInteger
from sqlalchemy.types import TypeDecorator


class ScaledDecimal(TypeDecorator[Decimal]):
    """Exact decimal stored as an integer count of 10^-scale units (qty 1.5 at scale 3 -> 1500).

    SQLite has no exact decimal type (Numeric degrades to float), so quantities and percentages
    are stored this way. SQL SUM() over the column stays exact and comes back as a Decimal."""

    impl = BigInteger
    cache_ok = True

    def __init__(self, scale: int) -> None:
        super().__init__()
        self.scale = scale
        self._factor = Decimal(10) ** scale
        self._quantum = Decimal(1).scaleb(-scale)

    def process_bind_param(self, value: Decimal | int | None, dialect) -> int | None:
        if value is None:
            return None
        scaled = Decimal(value) * self._factor
        if scaled != scaled.to_integral_value():
            raise ValueError(f"{value} has more than {self.scale} decimal places")
        return int(scaled)

    def process_result_value(self, value: int | None, dialect) -> Decimal | None:
        if value is None:
            return None
        return (Decimal(value) / self._factor).quantize(self._quantum)


Qty = ScaledDecimal(3)  # fractional units (kg, litres)
Fraction = ScaledDecimal(4)  # percentages as fractions: 0.2500 = 25%
