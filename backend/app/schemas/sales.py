from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field

from app.domain.sales import PaymentMethod
from app.schemas.common import Cents, Schema


class SaleLineIn(Schema):
    product_id: UUID
    qty: Decimal = Field(gt=0, decimal_places=3)
    # The unit price is always the product's current price (the server is authoritative).
    # Discounts are per line, in cents off the line amount.
    discount_cents: Cents = 0


class PaymentIn(Schema):
    method: PaymentMethod
    amount_cents: Cents
    mpesa_code: str | None = None  # required for M-Pesa, e.g. "SIB2XK7Q9M"


class SaleCreate(Schema):
    # Client-generated so a POS can safely retry: posting the same id again returns that sale.
    id: UUID = Field(default_factory=uuid4)
    device_id: str | None = None
    customer_id: UUID | None = None  # required when any payment is on credit
    lines: list[SaleLineIn] = Field(min_length=1)
    payments: list[PaymentIn] = Field(default_factory=list)
    # Owner only: required when any line's effective unit price is below the price floor.
    floor_override_reason: str | None = None
    # Owner only: required when a credit sale breaks the customer's limit or they have overdue
    # invoices (spec Part A §6).
    credit_override_reason: str | None = None


class SaleLineOut(Schema):
    id: UUID
    product_id: UUID
    qty: Decimal
    unit_price: int
    discount: int
    line_total: int
    wac_snapshot: int
    cogs: int
    gross_profit: int
    floor_override: bool
    returned_qty: Decimal


class PaymentOut(Schema):
    method: PaymentMethod
    amount: int
    mpesa_code: str | None


class SaleOut(Schema):
    id: UUID
    receipt_no: str
    subtotal: int
    discount_total: int
    total: int
    cogs: int
    gross_profit: int
    change_given: int
    status: str
    device_id: str | None
    customer_id: UUID | None
    user_id: UUID
    ts: datetime
    lines: list[SaleLineOut]
    payments: list[PaymentOut]
    refunded_total: int


class ReturnLineIn(Schema):
    sale_line_id: UUID
    qty: Decimal = Field(gt=0, decimal_places=3)


class ReturnCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    lines: list[ReturnLineIn] = Field(min_length=1)
    # cash / mpesa pay money back; credit reduces what a credit customer owes (credit note).
    refund_method: PaymentMethod
    refund_reference: str | None = None  # e.g. the M-Pesa reversal code
    reason: str = Field(min_length=1)


class ReturnLineOut(Schema):
    sale_line_id: UUID
    qty: Decimal
    refund: int
    cogs_reversed: int


class ReturnOut(Schema):
    id: UUID
    sale_id: UUID
    reason: str
    refund_method: PaymentMethod
    refund_reference: str | None
    refund_total: int
    cogs_reversed: int
    ts: datetime
    lines: list[ReturnLineOut]


class ReceiptOut(Schema):
    receipt_no: str
    text: str  # plain text, 32 columns wide: fits 58 mm printers and SMS/WhatsApp sharing


class AccountOut(Schema):
    id: UUID
    type: str
    name: str
    balance_cents: int
