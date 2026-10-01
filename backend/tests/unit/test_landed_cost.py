from decimal import Decimal

import pytest

from app.domain.landed_cost import (
    AllocationMethod,
    LineInput,
    SharedCostType,
    allocate_shared_costs,
    landed_unit_cost,
    missing_cost_types,
)


def test_allocates_by_line_value():
    lines = [LineInput(Decimal(10), 10_000), LineInput(Decimal(5), 40_000)]  # values 100k, 200k
    assert allocate_shared_costs(lines, 30_000, AllocationMethod.BY_VALUE) == [10_000, 20_000]


def test_allocates_by_quantity():
    lines = [LineInput(Decimal(10), 10_000), LineInput(Decimal(30), 1)]
    assert allocate_shared_costs(lines, 4_000, AllocationMethod.BY_QUANTITY) == [1_000, 3_000]


@pytest.mark.parametrize("method", list(AllocationMethod))
def test_remainder_cents_are_never_lost(method):
    lines = [LineInput(Decimal(1), 100)] * 3
    parts = allocate_shared_costs(lines, 1_000, method)
    assert sum(parts) == 1_000
    assert parts == [334, 333, 333]


def test_value_allocation_falls_back_to_quantity_when_all_lines_are_free():
    lines = [LineInput(Decimal(1), 0), LineInput(Decimal(3), 0)]
    assert allocate_shared_costs(lines, 400, AllocationMethod.BY_VALUE) == [100, 300]


def test_zero_shared_cost():
    assert allocate_shared_costs([LineInput(Decimal(2), 50)], 0, AllocationMethod.BY_VALUE) == [0]


def test_landed_unit_cost():
    # (BP x qty + allocated) / qty = (100 x 3 + 1000) / 3 = 433.33 -> 433
    assert landed_unit_cost(Decimal(3), 100, 1_000) == 433
    assert landed_unit_cost(Decimal("0.5"), 20_000, 500) == 21_000


def test_missing_cost_types_blocks_until_all_entered_or_zeroed():
    assert missing_cost_types({"transport", "duty"}) == [
        SharedCostType.PACKAGING,
        SharedCostType.OTHER,
    ]
    assert missing_cost_types({t.value for t in SharedCostType}) == []
