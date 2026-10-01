import datetime as dt
from uuid import UUID, uuid4

from pydantic import Field

from app.domain.credit import AgeingBucket
from app.domain.sales import PaymentMethod
from app.schemas.common import Cents, Schema


class CustomerCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)  # needed for SMS reminders
    id_number: str | None = Field(default=None, max_length=30)
    credit_limit_cents: Cents = 0
    terms_days: int = Field(default=30, ge=0, le=365)


class CustomerUpdate(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    id_number: str | None = Field(default=None, max_length=30)
    credit_limit_cents: Cents | None = None
    terms_days: int | None = Field(default=None, ge=0, le=365)
    active: bool | None = None


class CustomerOut(Schema):
    id: UUID
    name: str
    phone: str | None
    id_number: str | None
    credit_limit_cents: int
    terms_days: int
    active: bool
    balance_cents: int
    overdue_cents: int
    available_credit_cents: int  # limit - balance, never below 0


class InvoiceOut(Schema):
    charge_id: UUID
    sale_id: UUID | None
    receipt_no: str | None
    date: dt.datetime
    due_date: dt.date
    amount: int
    outstanding: int
    days_overdue: int
    bucket: AgeingBucket


class CreditEntryOut(Schema):
    id: UUID
    type: str
    amount: int
    due_date: dt.date | None
    sale_id: UUID | None
    account_id: UUID | None
    mpesa_code: str | None
    note: str | None
    user_id: UUID
    ts: dt.datetime


class StatementOut(Schema):
    customer: CustomerOut
    open_invoices: list[InvoiceOut]
    ageing: dict[AgeingBucket, int]
    entries: list[CreditEntryOut]


class RepaymentCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    amount_cents: Cents = Field(gt=0)
    method: PaymentMethod  # cash or mpesa
    mpesa_code: str | None = None
    note: str | None = None


class WriteOffCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    amount_cents: Cents = Field(gt=0)
    reason: str = Field(min_length=1)


class AgeingRow(Schema):
    customer_id: UUID
    name: str
    phone: str | None
    balance_cents: int
    buckets: dict[AgeingBucket, int]


class AgeingOut(Schema):
    as_of: dt.date
    rows: list[AgeingRow]  # only customers who owe something, largest balance first
    totals: dict[AgeingBucket, int]
    total_cents: int


class SmsOut(Schema):
    id: UUID
    phone: str
    message: str
    kind: str
    ref_type: str
    ref_id: UUID
    status: str
    created_at: dt.datetime
