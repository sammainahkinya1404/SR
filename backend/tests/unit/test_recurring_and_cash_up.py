from datetime import UTC, date, datetime

import pytest

from app.domain.cash_up import cash_up
from app.domain.clock import business_today
from app.domain.recurring import Frequency, due_dates, first_due, next_due, validate_day

MONTHLY, WEEKLY = Frequency.MONTHLY, Frequency.WEEKLY


def test_monthly_day_is_clamped_to_short_months():
    assert first_due(MONTHLY, 31, date(2026, 1, 15)) == date(2026, 1, 31)
    assert next_due(MONTHLY, 31, date(2026, 1, 31)) == date(2026, 2, 28)
    # Clamping never sticks: March goes back to the 31st.
    assert next_due(MONTHLY, 31, date(2026, 2, 28)) == date(2026, 3, 31)
    assert next_due(MONTHLY, 5, date(2026, 12, 5)) == date(2027, 1, 5)


def test_monthly_start_after_this_months_day_rolls_to_next_month():
    assert first_due(MONTHLY, 1, date(2026, 9, 29)) == date(2026, 10, 1)
    assert first_due(MONTHLY, 29, date(2026, 9, 29)) == date(2026, 9, 29)


def test_weekly():
    assert first_due(WEEKLY, 0, date(2026, 9, 29)) == date(2026, 10, 5)  # next Monday
    assert first_due(WEEKLY, 1, date(2026, 9, 29)) == date(2026, 9, 29)  # a Tuesday


def test_due_dates_catch_up_on_missed_runs():
    dates = list(due_dates(MONTHLY, 31, date(2026, 1, 31), date(2026, 4, 29)))
    assert dates == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    assert list(due_dates(MONTHLY, 31, date(2026, 4, 30), date(2026, 4, 29))) == []


@pytest.mark.parametrize("frequency, day", [(MONTHLY, 0), (MONTHLY, 32), (WEEKLY, 7)])
def test_day_validation(frequency, day):
    with pytest.raises(ValueError):
        validate_day(frequency, day)


def test_business_date_is_kenyan():
    assert business_today(datetime(2026, 9, 29, 21, 30, tzinfo=UTC)) == date(2026, 9, 30)


def test_cash_up_variance():
    short = cash_up(30_000, 29_500, "coins miscounted")
    assert (short.variance, short.shortage, short.overage) == (-500, 500, 0)
    over = cash_up(0, 100, "unrecorded sale")
    assert (over.variance, over.shortage, over.overage) == (100, 0, 100)
    assert cash_up(100, 100, None).variance == 0


def test_cash_up_variance_needs_explanation():
    with pytest.raises(ValueError, match="explanation"):
        cash_up(30_000, 29_500, "  ")
