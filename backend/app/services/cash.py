"""Accounts and the cash ledger (spec Part A §8). Every movement of money posts here; balances are
always summed from the ledger."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.sales import PaymentMethod
from app.models import Account, CashLedger
from app.schemas.finance import AccountCreate, AccountType
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, NotFound


class CashEntryType(StrEnum):
    SALE = "sale"
    REFUND = "refund"
    REPAYMENT = "repayment"  # a credit customer paying down their balance
    EXPENSE = "expense"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    CAPITAL = "capital"
    DRAWING = "drawing"
    CASH_UP_OVERAGE = "cash_up_overage"  # shortages post as expenses instead


DEFAULT_ACCOUNTS = [
    (AccountType.CASH, "Cash drawer"),
    (AccountType.MPESA, "M-Pesa till"),
    (AccountType.BANK, "Bank"),
]


def create_default_accounts(session: Session, business_id: UUID) -> None:
    for account_type, name in DEFAULT_ACCOUNTS:
        session.add(Account(business_id=business_id, type=account_type, name=name))


def create_account(session: Session, actor: Actor, data: AccountCreate) -> Account:
    require_owner(actor, "add accounts")
    if session.get(Account, data.id) is not None:
        raise Conflict("account already exists")
    account = Account(id=data.id, business_id=actor.business_id, type=data.type, name=data.name)
    session.add(account)
    session.flush()
    return account


def get_account(session: Session, account_id: UUID) -> Account:
    account = session.get(Account, account_id)
    if account is None:
        raise NotFound("account not found")
    return account


def account_for(session: Session, method: PaymentMethod) -> Account:
    """The account a payment method settles into: the oldest account of that type."""
    account = session.scalar(
        select(Account)
        .where(Account.type == AccountType(method.value))
        .order_by(Account.created_at, Account.id)
    )
    if account is None:
        raise NotFound(f"no {method} account")
    return account


def post(
    session: Session,
    actor: Actor,
    account: Account,
    entry_type: CashEntryType,
    amount: int,
    ref_type: str,
    ref_id: UUID,
    note: str | None = None,
) -> None:
    if amount == 0:
        return
    session.add(
        CashLedger(
            business_id=actor.business_id,
            account_id=account.id,
            type=entry_type,
            amount=amount,
            ref_type=ref_type,
            ref_id=ref_id,
            note=note,
            user_id=actor.user_id,
        )
    )


def balance(session: Session, account_id: UUID) -> int:
    session.flush()
    total = session.scalar(
        select(func.sum(CashLedger.amount)).where(CashLedger.account_id == account_id)
    )
    return total or 0


def balances(session: Session) -> list[tuple[Account, int]]:
    totals = dict(
        session.execute(
            select(CashLedger.account_id, func.sum(CashLedger.amount)).group_by(
                CashLedger.account_id
            )
        ).all()
    )
    accounts = session.scalars(select(Account).order_by(Account.type, Account.created_at))
    return [(a, totals.get(a.id, 0)) for a in accounts]


def ledger(
    session: Session, account_id: UUID, since: datetime | None, limit: int
) -> list[CashLedger]:
    get_account(session, account_id)
    stmt = (
        select(CashLedger)
        .where(CashLedger.account_id == account_id)
        .order_by(CashLedger.ts.desc(), CashLedger.id)
        .limit(limit)
    )
    if since is not None:
        stmt = stmt.where(CashLedger.ts >= since)
    return list(session.scalars(stmt))
