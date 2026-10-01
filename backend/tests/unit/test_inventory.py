from decimal import Decimal

from app.domain.inventory import new_wac, stock_value


def test_wac_blends_old_and_incoming_stock():
    # (10 x 100 + 30 x 200) / 40 = 175
    assert new_wac(Decimal(10), 100, Decimal(30), 200) == 175


def test_wac_rounds_half_up_to_the_cent():
    # (1 x 100 + 2 x 101) / 3 = 100.67
    assert new_wac(Decimal(1), 100, Decimal(2), 101) == 101


def test_wac_takes_landed_cost_when_shelf_is_empty_or_negative():
    assert new_wac(Decimal(0), 999, Decimal(5), 120) == 120
    assert new_wac(Decimal(-2), 999, Decimal(5), 120) == 120


def test_stock_value():
    assert stock_value(Decimal("2.5"), 1_001) == 2_503
