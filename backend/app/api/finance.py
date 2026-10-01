"""Expenses, transfers, owner capital/drawings, cash-ups and stock write-offs. All owner-only:
the services enforce it."""

import datetime as dt
from uuid import UUID

from fastapi import APIRouter

from app.api.deps import Ctx
from app.schemas.finance import (
    CapitalCreate,
    CashUpCreate,
    CashUpOut,
    CategoryCreate,
    CategoryOut,
    CategoryUpdate,
    DrawingCreate,
    DrawingOut,
    ExpenseCreate,
    ExpenseOut,
    OwnerEntryOut,
    ProfitOut,
    RecurringCreate,
    RecurringOut,
    RecurringUpdate,
    ReverseIn,
    StockAdjustmentCreate,
    StockAdjustmentOut,
    TransferCreate,
    TransferOut,
    WriteOffType,
)
from app.services import cash_ups, expenses, owner, reports, stock_adjustments, transfers
from app.services.actor import require_owner
from app.services.owner import DrawingResult, OwnerEntryType

router = APIRouter()


def _drawing_out(result: DrawingResult) -> DrawingOut:
    return DrawingOut(
        entry=OwnerEntryOut.model_validate(result.entry),
        drawings_to_date=result.drawings_to_date,
        net_profit_to_date=result.net_profit_to_date,
        warning=result.warning,
    )


# Expense categories -----------------------------------------------------------------------------


@router.get("/expense-categories", response_model=list[CategoryOut], tags=["expenses"])
def list_categories(ctx: Ctx):
    require_owner(ctx.actor, "view expense categories")
    return expenses.list_categories(ctx.session)


@router.post("/expense-categories", status_code=201, response_model=CategoryOut, tags=["expenses"])
def create_category(data: CategoryCreate, ctx: Ctx):
    return expenses.create_category(ctx.session, ctx.actor, data)


@router.patch("/expense-categories/{category_id}", response_model=CategoryOut, tags=["expenses"])
def update_category(category_id: UUID, data: CategoryUpdate, ctx: Ctx):
    return expenses.update_category(ctx.session, ctx.actor, category_id, data)


# Expenses ---------------------------------------------------------------------------------------


@router.post("/expenses", status_code=201, response_model=ExpenseOut, tags=["expenses"])
def create_expense(data: ExpenseCreate, ctx: Ctx):
    return expenses.create_expense(ctx.session, ctx.actor, data)


@router.get("/expenses", response_model=list[ExpenseOut], tags=["expenses"])
def list_expenses(
    ctx: Ctx,
    since: dt.date | None = None,
    until: dt.date | None = None,
    category_id: UUID | None = None,
):
    require_owner(ctx.actor, "view expenses")
    return expenses.list_expenses(ctx.session, since, until, category_id)


@router.get("/expenses/{expense_id}", response_model=ExpenseOut, tags=["expenses"])
def get_expense(expense_id: UUID, ctx: Ctx):
    require_owner(ctx.actor, "view expenses")
    return expenses.get_expense(ctx.session, expense_id)


@router.post(
    "/expenses/{expense_id}/reverse", status_code=201, response_model=ExpenseOut, tags=["expenses"]
)
def reverse_expense(expense_id: UUID, data: ReverseIn, ctx: Ctx):
    return expenses.reverse_expense(ctx.session, ctx.actor, expense_id, data.reason)


# Recurring expenses -----------------------------------------------------------------------------


@router.get("/recurring-expenses", response_model=list[RecurringOut], tags=["expenses"])
def list_recurring(ctx: Ctx):
    require_owner(ctx.actor, "view recurring expenses")
    return expenses.list_recurring(ctx.session)


@router.post("/recurring-expenses", status_code=201, response_model=RecurringOut, tags=["expenses"])
def create_recurring(data: RecurringCreate, ctx: Ctx):
    return expenses.create_recurring(ctx.session, ctx.actor, data)


@router.patch("/recurring-expenses/{recurring_id}", response_model=RecurringOut, tags=["expenses"])
def update_recurring(recurring_id: UUID, data: RecurringUpdate, ctx: Ctx):
    return expenses.update_recurring(ctx.session, ctx.actor, recurring_id, data)


@router.post("/recurring-expenses/run", response_model=list[ExpenseOut], tags=["expenses"])
def run_recurring(ctx: Ctx):
    """Post everything due up to today. The nightly job (`python -m app.jobs`) does the same."""
    require_owner(ctx.actor, "post recurring expenses")
    return expenses.post_due_recurring(ctx.session, ctx.actor)


# Transfers, capital, drawings -------------------------------------------------------------------


@router.post("/transfers", status_code=201, response_model=TransferOut, tags=["cash"])
def create_transfer(data: TransferCreate, ctx: Ctx):
    return transfers.create_transfer(ctx.session, ctx.actor, data)


@router.get("/transfers", response_model=list[TransferOut], tags=["cash"])
def list_transfers(ctx: Ctx):
    require_owner(ctx.actor, "view transfers")
    return transfers.list_transfers(ctx.session)


@router.post("/capital", status_code=201, response_model=OwnerEntryOut, tags=["owner"])
def record_opening_capital(data: CapitalCreate, ctx: Ctx):
    return owner.record_opening_capital(ctx.session, ctx.actor, data)


@router.post("/drawings", status_code=201, response_model=DrawingOut, tags=["owner"])
def record_drawing(data: DrawingCreate, ctx: Ctx):
    return _drawing_out(owner.record_drawing(ctx.session, ctx.actor, data))


@router.get("/owner-entries", response_model=list[OwnerEntryOut], tags=["owner"])
def list_owner_entries(ctx: Ctx, type: OwnerEntryType | None = None):
    require_owner(ctx.actor, "view capital and drawings")
    return owner.list_entries(ctx.session, type)


@router.get("/profit-to-date", response_model=ProfitOut, tags=["owner"])
def profit_to_date(ctx: Ctx):
    require_owner(ctx.actor, "view profit")
    return reports.profit_to_date(ctx.session)


# Cash-up ----------------------------------------------------------------------------------------


@router.post("/cash-ups", status_code=201, response_model=CashUpOut, tags=["cash"])
def create_cash_up(data: CashUpCreate, ctx: Ctx):
    return cash_ups.create_cash_up(ctx.session, ctx.actor, data)


@router.get("/cash-ups", response_model=list[CashUpOut], tags=["cash"])
def list_cash_ups(ctx: Ctx, since: dt.date | None = None):
    require_owner(ctx.actor, "view cash-ups")
    return cash_ups.list_cash_ups(ctx.session, since)


# Stock write-offs -------------------------------------------------------------------------------


@router.post(
    "/stock-adjustments", status_code=201, response_model=StockAdjustmentOut, tags=["stock"]
)
def write_off_stock(data: StockAdjustmentCreate, ctx: Ctx):
    result = stock_adjustments.write_off(ctx.session, ctx.actor, data)
    return StockAdjustmentOut(
        movement_id=result.movement.id,
        product_id=result.movement.product_id,
        type=WriteOffType(result.movement.type),
        qty=-result.movement.qty,
        value_cents=result.value,
        expense_id=result.expense.id if result.expense else None,
        drawing=_drawing_out(result.drawing) if result.drawing else None,
    )
