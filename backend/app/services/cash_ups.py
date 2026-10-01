"""Daily cash-up (spec Part A §8, Part B §5): compare the ledger's expected balance with what was
counted, and post the variance so the ledger matches reality again."""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import cash_up as rules
from app.domain.clock import business_today
from app.models import CashUp
from app.schemas.finance import CashUpCreate
from app.services import cash, expenses
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, RuleViolation


def create_cash_up(session: Session, actor: Actor, data: CashUpCreate) -> CashUp:
    require_owner(actor, "do the cash-up")
    account = cash.get_account(session, data.account_id)
    date = data.date or business_today()
    if session.scalar(
        select(CashUp.id).where(CashUp.account_id == account.id, CashUp.date == date)
    ):
        raise Conflict(f"{account.name} was already cashed up for {date}")

    expected = cash.balance(session, account.id)
    try:
        result = rules.cash_up(expected, data.counted_cents, data.explanation)
    except ValueError as e:
        raise RuleViolation(str(e)) from e

    record = CashUp(
        id=data.id,
        business_id=actor.business_id,
        account_id=account.id,
        date=date,
        expected=result.expected,
        counted=result.counted,
        variance=result.variance,
        explanation=data.explanation,
        user_id=actor.user_id,
    )
    session.add(record)
    session.flush()
    if result.shortage:
        # Missing money is a loss, so it reduces profit like any other expense.
        expenses.post_expense(
            session,
            actor,
            date=date,
            category=expenses.category_named(session, expenses.CASH_SHORTAGE),
            amount=result.shortage,
            account_id=account.id,
            note=data.explanation,
            source=expenses.ExpenseSource.CASH_SHORTAGE,
            ref_type="cash_up",
            ref_id=record.id,
        )
    elif result.overage:
        cash.post(
            session,
            actor,
            account,
            cash.CashEntryType.CASH_UP_OVERAGE,
            result.overage,
            "cash_up",
            record.id,
            note=data.explanation,
        )
    return record


def list_cash_ups(session: Session, since: dt.date | None) -> list[CashUp]:
    stmt = select(CashUp).order_by(CashUp.date.desc(), CashUp.ts.desc())
    if since is not None:
        stmt = stmt.where(CashUp.date >= since)
    return list(session.scalars(stmt))
