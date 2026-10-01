"""Owner capital and drawings (spec Part A §8). Equity movements: they change cash but are never
income or expenses, so they never touch profit."""

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.clock import business_today
from app.models import OwnerEntry
from app.schemas.finance import CapitalCreate, DrawingCreate
from app.services import cash
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict
from app.services.reports import profit_to_date


class OwnerEntryType(StrEnum):
    OPENING_CAPITAL = "opening_capital"
    DRAWING = "drawing"


@dataclass(frozen=True)
class DrawingResult:
    entry: OwnerEntry
    drawings_to_date: int
    net_profit_to_date: int

    @property
    def warning(self) -> str | None:
        if self.drawings_to_date > self.net_profit_to_date:
            return (
                f"Drawings to date ({self.drawings_to_date}) exceed net profit to date "
                f"({self.net_profit_to_date}): the owner is taking out more than the business "
                "has earned."
            )
        return None


def record_opening_capital(session: Session, actor: Actor, data: CapitalCreate) -> OwnerEntry:
    """The owner's one-time starting contribution."""
    require_owner(actor, "record opening capital")
    if session.scalar(
        select(OwnerEntry.id).where(OwnerEntry.type == OwnerEntryType.OPENING_CAPITAL)
    ):
        raise Conflict("opening capital has already been recorded")
    account = cash.get_account(session, data.account_id)
    entry = _add(
        session,
        actor,
        OwnerEntryType.OPENING_CAPITAL,
        data.amount_cents,
        account.id,
        data.date,
        data.note,
        data.id,
    )
    cash.post(
        session, actor, account, cash.CashEntryType.CAPITAL, entry.amount, "owner_entry", entry.id
    )
    return entry


def record_drawing(session: Session, actor: Actor, data: DrawingCreate) -> DrawingResult:
    require_owner(actor, "record drawings")
    if session.get(OwnerEntry, data.id) is not None:
        raise Conflict("drawing already exists")
    account = cash.get_account(session, data.account_id)
    entry = _add(
        session,
        actor,
        OwnerEntryType.DRAWING,
        data.amount_cents,
        account.id,
        data.date,
        data.note,
        data.id,
    )
    cash.post(
        session, actor, account, cash.CashEntryType.DRAWING, -entry.amount, "owner_entry", entry.id
    )
    return summarize(session, entry)


def record_stock_drawing(
    session: Session, actor: Actor, amount: int, note: str | None
) -> DrawingResult:
    """Goods taken for personal use: a drawing in kind at cost, with no account movement."""
    entry = _add(session, actor, OwnerEntryType.DRAWING, amount, None, None, note, None)
    return summarize(session, entry)


def summarize(session: Session, entry: OwnerEntry) -> DrawingResult:
    profit = profit_to_date(session)
    return DrawingResult(entry, profit.drawings, profit.net_profit)


def list_entries(session: Session, entry_type: OwnerEntryType | None) -> list[OwnerEntry]:
    stmt = select(OwnerEntry).order_by(OwnerEntry.date.desc(), OwnerEntry.ts.desc())
    if entry_type is not None:
        stmt = stmt.where(OwnerEntry.type == entry_type)
    return list(session.scalars(stmt))


def _add(
    session: Session,
    actor: Actor,
    entry_type: OwnerEntryType,
    amount: int,
    account_id: UUID | None,
    date: dt.date | None,
    note: str | None,
    entry_id: UUID | None,
) -> OwnerEntry:
    entry = OwnerEntry(
        business_id=actor.business_id,
        type=entry_type,
        date=date or business_today(),
        amount=amount,
        account_id=account_id,
        note=note,
        user_id=actor.user_id,
    )
    if entry_id is not None:
        entry.id = entry_id
    session.add(entry)
    session.flush()
    return entry
