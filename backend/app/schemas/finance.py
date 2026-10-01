import datetime as dt
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field

from app.domain.recurring import Frequency
from app.schemas.common import Cents, Schema


class AccountType(StrEnum):
    CASH = "cash"
    MPESA = "mpesa"
    BANK = "bank"


class AccountCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    type: AccountType
    name: str = Field(min_length=1, max_length=100)


class LedgerEntryOut(Schema):
    id: UUID
    type: str
    amount: int
    ref_type: str | None
    ref_id: UUID | None
    note: str | None
    user_id: UUID
    ts: dt.datetime


# Expenses ---------------------------------------------------------------------------------------


class CategoryCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=100)
    is_fixed: bool = False


class CategoryUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_fixed: bool | None = None
    active: bool | None = None


class CategoryOut(Schema):
    id: UUID
    name: str
    is_fixed: bool
    system: bool
    active: bool


class ExpenseCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    date: dt.date | None = None  # defaults to today in Kenya
    category_id: UUID
    amount_cents: Cents = Field(gt=0)
    account_id: UUID
    is_fixed: bool | None = None  # defaults to the category's flag
    note: str | None = None
    # Link to a receipt photo stored elsewhere; file upload/storage is an integration for later.
    receipt_url: str | None = Field(default=None, max_length=500)


class ExpenseOut(Schema):
    id: UUID
    date: dt.date
    category_id: UUID
    amount: int
    account_id: UUID | None
    is_fixed: bool
    note: str | None
    receipt_url: str | None
    source: str
    ref_type: str | None
    ref_id: UUID | None
    recurring_id: UUID | None
    reverses_id: UUID | None
    user_id: UUID
    ts: dt.datetime


class ReverseIn(Schema):
    reason: str = Field(min_length=1)


class RecurringCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    category_id: UUID
    amount_cents: Cents = Field(gt=0)
    account_id: UUID
    is_fixed: bool | None = None
    note: str | None = None
    frequency: Frequency
    day: int  # monthly: day of month 1-31; weekly: 0 = Monday ... 6 = Sunday
    start_date: dt.date | None = None  # first occurrence is on or after this; default today


class RecurringUpdate(Schema):
    """Amount, account and on/off can change. To change the schedule, create a new one."""

    amount_cents: Cents | None = Field(default=None, gt=0)
    account_id: UUID | None = None
    is_fixed: bool | None = None
    note: str | None = None
    active: bool | None = None


class RecurringOut(Schema):
    id: UUID
    category_id: UUID
    amount: int
    account_id: UUID
    is_fixed: bool
    note: str | None
    frequency: Frequency
    day: int
    next_due: dt.date
    active: bool


# Transfers, capital, drawings, cash-up ----------------------------------------------------------


class TransferCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    date: dt.date | None = None
    from_account_id: UUID
    to_account_id: UUID
    amount_cents: Cents = Field(gt=0)
    fee_cents: Cents = 0  # e.g. M-Pesa withdrawal charge, posted as an expense
    note: str | None = None


class TransferOut(Schema):
    id: UUID
    date: dt.date
    from_account_id: UUID
    to_account_id: UUID
    amount: int
    fee: int
    note: str | None
    user_id: UUID
    ts: dt.datetime


class CapitalCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    date: dt.date | None = None
    account_id: UUID
    amount_cents: Cents = Field(gt=0)
    note: str | None = None


class DrawingCreate(CapitalCreate):
    pass


class OwnerEntryOut(Schema):
    id: UUID
    type: str
    date: dt.date
    amount: int
    account_id: UUID | None
    note: str | None
    user_id: UUID
    ts: dt.datetime


class DrawingOut(Schema):
    entry: OwnerEntryOut
    drawings_to_date: int
    net_profit_to_date: int
    warning: str | None  # set when drawings exceed net profit to date (spec Part A §8)


class CashUpCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    account_id: UUID
    date: dt.date | None = None
    counted_cents: int
    explanation: str | None = None  # required when counted differs from expected


class CashUpOut(Schema):
    id: UUID
    account_id: UUID
    date: dt.date
    expected: int
    counted: int
    variance: int
    explanation: str | None
    user_id: UUID
    ts: dt.datetime


class ProfitOut(Schema):
    gross_profit: int
    operating_expenses: int
    net_profit: int
    drawings: int


# Stock write-offs -------------------------------------------------------------------------------


class WriteOffType(StrEnum):
    DAMAGE = "damage"
    THEFT = "theft"
    OWNER_CONSUMPTION = "owner_consumption"


class StockAdjustmentCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    product_id: UUID
    type: WriteOffType
    qty: Decimal = Field(gt=0, decimal_places=3)
    reason: str = Field(min_length=1)


class StockAdjustmentOut(Schema):
    movement_id: UUID
    product_id: UUID
    type: WriteOffType
    qty: Decimal
    value_cents: int  # qty x WAC
    expense_id: UUID | None  # damage / theft
    drawing: DrawingOut | None  # owner consumption
