"""Schedules for recurring expenses (spec Part A §7): monthly on a day of the month, or weekly on
a weekday."""

import calendar
from collections.abc import Iterator
from datetime import date, timedelta
from enum import StrEnum


class Frequency(StrEnum):
    MONTHLY = "monthly"  # day: 1-31, clamped to the month's last day (31 -> 30 Apr, 28 Feb)
    WEEKLY = "weekly"  # day: 0 = Monday ... 6 = Sunday


def validate_day(frequency: Frequency, day: int) -> None:
    low, high = (1, 31) if frequency is Frequency.MONTHLY else (0, 6)
    if not low <= day <= high:
        raise ValueError(f"{frequency} day must be between {low} and {high}")


def _monthly(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def first_due(frequency: Frequency, day: int, start: date) -> date:
    """The first scheduled date on or after `start`."""
    if frequency is Frequency.WEEKLY:
        return start + timedelta(days=(day - start.weekday()) % 7)
    candidate = _monthly(start.year, start.month, day)
    return candidate if candidate >= start else next_due(frequency, day, candidate)


def next_due(frequency: Frequency, day: int, current: date) -> date:
    """The scheduled date after `current`."""
    if frequency is Frequency.WEEKLY:
        return current + timedelta(days=7)
    year, month = (
        (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
    )
    return _monthly(year, month, day)


def due_dates(frequency: Frequency, day: int, due: date, today: date) -> Iterator[date]:
    """Every scheduled date from `due` up to and including `today`, so missed runs catch up."""
    while due <= today:
        yield due
        due = next_due(frequency, day, due)
