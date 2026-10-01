"""Expenses, categories and recurring expenses (spec Part A §7)."""

import datetime as dt
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import recurring as schedule
from app.domain.clock import business_today
from app.models import Expense, ExpenseCategory, RecurringExpense
from app.schemas.finance import (
    CategoryCreate,
    CategoryUpdate,
    ExpenseCreate,
    RecurringCreate,
    RecurringUpdate,
)
from app.services import audit, cash
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, NotFound, RuleViolation


class ExpenseSource(StrEnum):
    MANUAL = "manual"
    RECURRING = "recurring"
    TRANSFER_FEE = "transfer_fee"
    STOCK_LOSS = "stock_loss"
    CASH_SHORTAGE = "cash_shortage"
    BAD_DEBT = "bad_debt"
    REVERSAL = "reversal"


# Spec defaults. Fixed costs feed break-even, so the regular overheads start out fixed.
DEFAULT_CATEGORIES = [
    ("Rent", True),
    ("Salaries", True),
    ("Electricity", True),
    ("Internet", True),
    ("Transport", False),
    ("M-Pesa charges", False),
    ("Packaging", False),
    ("Repairs", False),
    ("Other", False),
]
STOCK_LOSS = "Stock loss"
CASH_SHORTAGE = "Cash shortage"
BAD_DEBT = "Bad debt"
SYSTEM_CATEGORIES = [STOCK_LOSS, CASH_SHORTAGE, BAD_DEBT]
MPESA_CHARGES = "M-Pesa charges"

# Only these can be reversed directly; automatic postings are corrected through their own flow.
REVERSIBLE = {ExpenseSource.MANUAL, ExpenseSource.RECURRING}


def create_default_categories(session: Session, business_id: UUID) -> None:
    for name, is_fixed in DEFAULT_CATEGORIES:
        session.add(ExpenseCategory(business_id=business_id, name=name, is_fixed=is_fixed))
    for name in SYSTEM_CATEGORIES:
        session.add(
            ExpenseCategory(business_id=business_id, name=name, is_fixed=False, system=True)
        )


def category_named(session: Session, name: str) -> ExpenseCategory:
    category = session.scalar(select(ExpenseCategory).where(ExpenseCategory.name == name))
    if category is None:
        raise NotFound(f"expense category {name!r} not found")
    return category


def get_category(session: Session, category_id: UUID) -> ExpenseCategory:
    category = session.get(ExpenseCategory, category_id)
    if category is None:
        raise NotFound("expense category not found")
    return category


def list_categories(session: Session) -> list[ExpenseCategory]:
    return list(session.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name)))


def create_category(session: Session, actor: Actor, data: CategoryCreate) -> ExpenseCategory:
    require_owner(actor, "manage expense categories")
    if session.scalar(select(ExpenseCategory.id).where(ExpenseCategory.name == data.name)):
        raise Conflict(f"category {data.name!r} already exists")
    category = ExpenseCategory(
        id=data.id, business_id=actor.business_id, name=data.name, is_fixed=data.is_fixed
    )
    session.add(category)
    session.flush()
    return category


def update_category(
    session: Session, actor: Actor, category_id: UUID, data: CategoryUpdate
) -> ExpenseCategory:
    require_owner(actor, "manage expense categories")
    category = get_category(session, category_id)
    if category.system:
        raise RuleViolation("system categories cannot be changed")
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(category, field, value)
    return category


def post_expense(
    session: Session,
    actor: Actor,
    *,
    date: dt.date,
    category: ExpenseCategory,
    amount: int,
    account_id: UUID | None,
    is_fixed: bool | None = None,
    note: str | None = None,
    receipt_url: str | None = None,
    source: ExpenseSource,
    ref_type: str | None = None,
    ref_id: UUID | None = None,
    recurring_id: UUID | None = None,
    reverses_id: UUID | None = None,
    expense_id: UUID | None = None,
) -> Expense:
    """Record an expense and, when it is paid from an account, take the money out of it."""
    expense = Expense(
        business_id=actor.business_id,
        date=date,
        category_id=category.id,
        amount=amount,
        account_id=account_id,
        is_fixed=category.is_fixed if is_fixed is None else is_fixed,
        note=note,
        receipt_url=receipt_url,
        source=source,
        ref_type=ref_type,
        ref_id=ref_id,
        recurring_id=recurring_id,
        reverses_id=reverses_id,
        user_id=actor.user_id,
    )
    if expense_id is not None:
        expense.id = expense_id
    session.add(expense)
    session.flush()
    if account_id is not None:
        account = cash.get_account(session, account_id)
        cash.post(
            session, actor, account, cash.CashEntryType.EXPENSE, -amount, "expense", expense.id
        )
    return expense


def create_expense(session: Session, actor: Actor, data: ExpenseCreate) -> Expense:
    require_owner(actor, "record expenses")
    if session.get(Expense, data.id) is not None:
        raise Conflict("expense already exists")
    category = get_category(session, data.category_id)
    if category.system or not category.active:
        raise RuleViolation(f"category {category.name!r} cannot be used for manual expenses")
    cash.get_account(session, data.account_id)
    return post_expense(
        session,
        actor,
        date=data.date or business_today(),
        category=category,
        amount=data.amount_cents,
        account_id=data.account_id,
        is_fixed=data.is_fixed,
        note=data.note,
        receipt_url=data.receipt_url,
        source=ExpenseSource.MANUAL,
        expense_id=data.id,
    )


def get_expense(session: Session, expense_id: UUID) -> Expense:
    expense = session.get(Expense, expense_id)
    if expense is None:
        raise NotFound("expense not found")
    return expense


def list_expenses(
    session: Session,
    since: dt.date | None,
    until: dt.date | None,
    category_id: UUID | None,
) -> list[Expense]:
    stmt = select(Expense).order_by(Expense.date.desc(), Expense.ts.desc())
    if since is not None:
        stmt = stmt.where(Expense.date >= since)
    if until is not None:
        stmt = stmt.where(Expense.date <= until)
    if category_id is not None:
        stmt = stmt.where(Expense.category_id == category_id)
    return list(session.scalars(stmt))


def reverse_expense(session: Session, actor: Actor, expense_id: UUID, reason: str) -> Expense:
    """Cancel an expense by posting its opposite; the original row is never touched."""
    require_owner(actor, "reverse expenses")
    original = get_expense(session, expense_id)
    if original.source not in REVERSIBLE:
        raise RuleViolation(f"{original.source} expenses are corrected through their own flow")
    if session.scalar(select(Expense.id).where(Expense.reverses_id == original.id)):
        raise Conflict("expense is already reversed")
    return post_expense(
        session,
        actor,
        date=business_today(),
        category=get_category(session, original.category_id),
        amount=-original.amount,
        account_id=original.account_id,
        is_fixed=original.is_fixed,
        note=f"Reversal: {reason}",
        source=ExpenseSource.REVERSAL,
        reverses_id=original.id,
    )


# Recurring expenses -----------------------------------------------------------------------------


def create_recurring(session: Session, actor: Actor, data: RecurringCreate) -> RecurringExpense:
    require_owner(actor, "set up recurring expenses")
    if session.get(RecurringExpense, data.id) is not None:
        raise Conflict("recurring expense already exists")
    category = get_category(session, data.category_id)
    if category.system:
        raise RuleViolation("system categories cannot be used for recurring expenses")
    cash.get_account(session, data.account_id)
    try:
        schedule.validate_day(data.frequency, data.day)
    except ValueError as e:
        raise RuleViolation(str(e)) from e
    item = RecurringExpense(
        id=data.id,
        business_id=actor.business_id,
        category_id=category.id,
        amount=data.amount_cents,
        account_id=data.account_id,
        is_fixed=category.is_fixed if data.is_fixed is None else data.is_fixed,
        note=data.note,
        frequency=data.frequency,
        day=data.day,
        next_due=schedule.first_due(data.frequency, data.day, data.start_date or business_today()),
        active=True,
        created_by=actor.user_id,
    )
    session.add(item)
    session.flush()
    return item


def get_recurring(session: Session, recurring_id: UUID) -> RecurringExpense:
    item = session.get(RecurringExpense, recurring_id)
    if item is None:
        raise NotFound("recurring expense not found")
    return item


def list_recurring(session: Session) -> list[RecurringExpense]:
    return list(session.scalars(select(RecurringExpense).order_by(RecurringExpense.next_due)))


def update_recurring(
    session: Session, actor: Actor, recurring_id: UUID, data: RecurringUpdate
) -> RecurringExpense:
    require_owner(actor, "change recurring expenses")
    item = get_recurring(session, recurring_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "amount_cents" in changes:
        changes["amount"] = changes.pop("amount_cents")
    if "account_id" in changes:
        cash.get_account(session, changes["account_id"])
    reactivated = changes.get("active") is True and not item.active
    for field, value in changes.items():
        if getattr(item, field) != value:
            old = getattr(item, field)
            audit.record(session, actor, "recurring_expense", item.id, field, old, value)
            setattr(item, field, value)
    if reactivated:
        # Resume from today rather than back-posting every period it was paused.
        today = business_today()
        if item.next_due < today:
            frequency = schedule.Frequency(item.frequency)
            item.next_due = schedule.first_due(frequency, item.day, today)
    return item


def post_due_recurring(
    session: Session, actor: Actor, today: dt.date | None = None
) -> list[Expense]:
    """Post every scheduled occurrence up to today, catching up on missed runs.

    Safe to run any number of times: each occurrence posts once (unique recurring_id + date)."""
    today = today or business_today()
    posted = []
    due_items = session.scalars(
        select(RecurringExpense)
        .where(RecurringExpense.active, RecurringExpense.next_due <= today)
        .with_for_update()
    ).all()
    for item in due_items:
        category = get_category(session, item.category_id)
        frequency = schedule.Frequency(item.frequency)
        for date in schedule.due_dates(frequency, item.day, item.next_due, today):
            posted.append(
                post_expense(
                    session,
                    actor,
                    date=date,
                    category=category,
                    amount=item.amount,
                    account_id=item.account_id,
                    is_fixed=item.is_fixed,
                    note=item.note,
                    source=ExpenseSource.RECURRING,
                    recurring_id=item.id,
                )
            )
            item.next_due = schedule.next_due(frequency, item.day, date)
    return posted
