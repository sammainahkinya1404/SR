from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import Ctx
from app.schemas.finance import AccountCreate, LedgerEntryOut
from app.schemas.sales import AccountOut
from app.services import cash
from app.services.actor import require_owner

router = APIRouter(prefix="/accounts", tags=["cash"])


@router.get("", response_model=list[AccountOut])
def list_accounts(ctx: Ctx):
    require_owner(ctx.actor, "view account balances")
    return [
        AccountOut(id=a.id, type=a.type, name=a.name, balance_cents=balance)
        for a, balance in cash.balances(ctx.session)
    ]


@router.post("", status_code=201, response_model=AccountOut)
def create_account(data: AccountCreate, ctx: Ctx):
    account = cash.create_account(ctx.session, ctx.actor, data)
    return AccountOut(id=account.id, type=account.type, name=account.name, balance_cents=0)


@router.get("/{account_id}/ledger", response_model=list[LedgerEntryOut])
def account_ledger(
    account_id: UUID,
    ctx: Ctx,
    since: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
):
    require_owner(ctx.actor, "view account ledgers")
    return cash.ledger(ctx.session, account_id, since, limit)
