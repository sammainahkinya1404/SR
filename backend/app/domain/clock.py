from datetime import UTC, date, datetime, timedelta, timezone

# Kenya has no daylight saving, so a fixed offset is exact (and needs no tz database on Windows).
EAT = timezone(timedelta(hours=3), "EAT")


def business_today(now: datetime | None = None) -> date:
    """The trading date in Kenya. Timestamps are stored in UTC; dates are always EAT."""
    return (now or datetime.now(UTC)).astimezone(EAT).date()
