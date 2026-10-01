import threading
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    # Money is integer cents in BIGINT (spec Part B §3), so every `int` column is a BIGINT.
    type_annotation_map = {int: BigInteger, datetime: DateTime(timezone=True)}


class IdMixin:
    # Clients generate UUIDs (spec Part B §3) so offline replays are idempotent; the default is
    # only a fallback for records created server-side.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TenantMixin(IdMixin):
    """Every tenant table has business_id; db.tenant_session limits rows to the current business."""

    @declared_attr
    def business_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(ForeignKey("businesses.id"), index=True)


_clock_lock = threading.Lock()
_last_ts = datetime.min.replace(tzinfo=UTC)


def _utcnow() -> datetime:
    """Strictly increasing timestamps: ledgers are replayed in (ts, id) order, and two entries for
    one product made in the same instant (the Windows clock is coarse) would otherwise be ordered
    by random id, replaying the wrong final cost."""
    global _last_ts
    with _clock_lock:
        now = datetime.now(UTC)
        if now <= _last_ts:
            now = _last_ts + timedelta(microseconds=1)
        _last_ts = now
        return now


def created_at_column() -> Mapped[datetime]:
    # Set in Python: SQLite's CURRENT_TIMESTAMP only has one-second resolution, which would make
    # ledger ordering by timestamp ambiguous.
    return mapped_column(default=_utcnow)
