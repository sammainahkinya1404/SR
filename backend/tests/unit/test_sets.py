from decimal import Decimal

import pytest

from app.domain.sets import Component, split_set_cost

SUFURIA = [Component(Decimal(1), p) for p in (20_000, 25_000, 30_000, 35_000, 40_000)]


def test_set_cost_is_shared_by_selling_price():
    # Sizes priced KSh 200-400 (KSh 1,500 for the set) bought at KSh 1,200: every size costs 80%
    # of its price, so all earn the same 20% margin.
    split = split_set_cost(SUFURIA, 120_000, Decimal(1))
    assert split.unit_costs == [16_000, 20_000, 24_000, 28_000, 32_000]
    assert split.remainder == 0


def test_rounding_is_kept_exact():
    dinner = [Component(Decimal(6), p) for p in (15_000, 12_000, 13_000, 9_000)]
    split = split_set_cost(dinner, 262_685, Decimal(2))
    booked = sum(u * c.qty * 2 for u, c in zip(split.unit_costs, dinner, strict=True))
    assert booked + split.remainder == 2 * 262_685
    assert 0 <= split.remainder < sum(c.qty * 2 for c in dinner)


def test_every_component_needs_a_price():
    with pytest.raises(ValueError, match="selling price"):
        split_set_cost([Component(Decimal(1), 100), Component(Decimal(1), 0)], 100, Decimal(1))
