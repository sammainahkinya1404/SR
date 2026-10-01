from decimal import Decimal

import pytest

from app.domain.pricing import (
    PricingMode,
    floor_price,
    margin,
    markup,
    price_from_cost,
    round_to_increment,
    suggest_price,
    wac_change_exceeds,
)


def test_target_margin_and_markup_formulas():
    assert price_from_cost(PricingMode.TARGET_MARGIN, 7_500, Decimal("0.25")) == 10_000
    assert price_from_cost(PricingMode.MARKUP, 8_000, Decimal("0.25")) == 10_000


@pytest.mark.parametrize("bad", [Decimal(1), Decimal("-0.1")])
def test_target_margin_must_be_below_100_percent(bad):
    with pytest.raises(ValueError):
        price_from_cost(PricingMode.TARGET_MARGIN, 100, bad)


def test_rounds_up_to_the_increment():
    assert round_to_increment(Decimal(10_001), 500) == 10_500
    assert round_to_increment(Decimal(10_000), 500) == 10_000  # exact multiples stay
    assert round_to_increment(Decimal("123.1"), 1) == 124


def test_rounding_up_never_drops_below_the_target_margin():
    # Cost KSh 21.25 at a 20% target is KSh 26.5625: nearest-KSh-5 would give 25 (15% margin).
    price = round_to_increment(
        price_from_cost(PricingMode.TARGET_MARGIN, 2_125, Decimal("0.2")), 500
    )
    assert price == 3_000
    assert margin(price, 2_125) >= Decimal("0.2")


def test_margin_and_markup_side_by_side():
    assert margin(10_000, 7_500) == Decimal("0.25")
    assert markup(10_000, 7_500) == Decimal(2_500) / 7_500
    assert margin(0, 100) is None
    assert markup(100, 0) is None


def test_floor_rounds_up():
    assert floor_price(1_001, Decimal("0.10")) == 1_102  # 1101.1 -> 1102


def test_wac_change_threshold():
    assert not wac_change_exceeds(10_000, 10_500, Decimal("0.05"))  # exactly 5% is not "more than"
    assert wac_change_exceeds(10_000, 10_501, Decimal("0.05"))
    assert wac_change_exceeds(10_000, 9_000, Decimal("0.05"))
    assert wac_change_exceeds(0, 100, Decimal("0.05"))


def test_rule_based_suggestion_reapplies_rule():
    suggested = suggest_price(
        mode=PricingMode.TARGET_MARGIN,
        target=Decimal("0.20"),
        new_wac=8_000,
        old_wac=7_000,
        current_price=9_000,
        increment=500,
    )
    assert suggested == 10_000


def test_manual_suggestion_keeps_previous_margin():
    # Old margin (10000 - 8000) / 10000 = 20%; new WAC 9000 / 0.8 = 11250 -> nearest 500 = 11500
    suggested = suggest_price(
        mode=PricingMode.MANUAL,
        target=None,
        new_wac=9_000,
        old_wac=8_000,
        current_price=10_000,
        increment=500,
    )
    assert suggested == 11_500


def test_manual_suggestion_needs_a_previous_cost():
    kwargs = dict(mode=PricingMode.MANUAL, target=None, new_wac=100, increment=1)
    assert suggest_price(old_wac=0, current_price=500, **kwargs) is None
