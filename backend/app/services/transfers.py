"""Moving money between accounts, e.g. banking the day's cash or withdrawing from M-Pesa."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.clock import business_today
from app.models import Transfer
from app.schemas.finance import TransferCreate
from app.services import cash, expenses
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, RuleViolation


def create_transfer(session: Session, actor: Actor, data: TransferCreate) -> Transfer:
    require_owner(actor, "transfer money between accounts")
    if session.get(Transfer, data.id) is not None:
        raise Conflict("transfer already exists")
    if data.from_account_id == data.to_account_id:
        raise RuleViolation("choose two different accounts")
    source = cash.get_account(session, data.from_account_id)
    target = cash.get_account(session, data.to_account_id)
    date = data.date or business_today()

    transfer = Transfer(
        id=data.id,
        business_id=actor.business_id,
        date=date,
        from_account_id=source.id,
        to_account_id=target.id,
        amount=data.amount_cents,
        fee=data.fee_cents,
        note=data.note,
        user_id=actor.user_id,
    )
    session.add(transfer)
    session.flush()
    kind = cash.CashEntryType
    cash.post(session, actor, source, kind.TRANSFER_OUT, -transfer.amount, "transfer", transfer.id)
    cash.post(session, actor, target, kind.TRANSFER_IN, transfer.amount, "transfer", transfer.id)
    if transfer.fee:
        # The fee is a real cost of doing business (e.g. M-Pesa withdrawal charges).
        expenses.post_expense(
            session,
            actor,
            date=date,
            category=expenses.category_named(session, expenses.MPESA_CHARGES),
            amount=transfer.fee,
            account_id=source.id,
            note=f"Fee on transfer to {target.name}",
            source=expenses.ExpenseSource.TRANSFER_FEE,
            ref_type="transfer",
            ref_id=transfer.id,
        )
    return transfer


def list_transfers(session: Session) -> list[Transfer]:
    return list(
        session.scalars(select(Transfer).order_by(Transfer.date.desc(), Transfer.ts.desc()))
    )
