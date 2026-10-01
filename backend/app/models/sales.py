import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, created_at_column
from app.models.types import Qty


class Sale(TenantMixin, Base):
    __tablename__ = "sales"
    __table_args__ = (UniqueConstraint("business_id", "receipt_no"),)

    receipt_no: Mapped[int]
    # Required for credit payments; optional otherwise.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("customers.id"), index=True)
    subtotal: Mapped[int]  # before discounts
    discount_total: Mapped[int]
    total: Mapped[int]
    cogs: Mapped[int]
    gross_profit: Mapped[int]
    change_given: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="completed")
    device_id: Mapped[str | None] = mapped_column(String(100))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()

    lines: Mapped[list["SaleLine"]] = relationship(order_by="SaleLine.position")
    payments: Mapped[list["Payment"]] = relationship(order_by="Payment.position")


class SaleLine(TenantMixin, Base):
    __tablename__ = "sale_lines"

    sale_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    qty: Mapped[Decimal] = mapped_column(Qty)
    unit_price: Mapped[int]
    discount: Mapped[int]
    line_total: Mapped[int]  # qty x unit price - discount
    # Cost snapshot: historical profit never changes when WAC moves later (spec Part B §3).
    wac_snapshot: Mapped[int]
    cogs: Mapped[int]
    gross_profit: Mapped[int]
    floor_price: Mapped[int]
    floor_override: Mapped[bool] = mapped_column(default=False)


class Payment(TenantMixin, Base):
    __tablename__ = "payments"
    # An M-Pesa code can only pay for one sale.
    __table_args__ = (UniqueConstraint("business_id", "mpesa_code"),)

    sale_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(20))  # PaymentMethod
    amount: Mapped[int]  # as tendered; change is recorded on the sale
    mpesa_code: Mapped[str | None] = mapped_column(String(20))
    # None for credit: the money is owed, it has not arrived anywhere yet.
    account_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("accounts.id"))


class SaleReturn(TenantMixin, Base):
    """A return links to its original sale and reverses its stock and cash (spec Part A §5)."""

    __tablename__ = "sale_returns"

    sale_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sales.id"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    refund_method: Mapped[str] = mapped_column(String(20))  # PaymentMethod (cash / mpesa)
    refund_reference: Mapped[str | None] = mapped_column(String(50))
    refund_total: Mapped[int]
    cogs_reversed: Mapped[int]
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()

    lines: Mapped[list["ReturnLine"]] = relationship()


class ReturnLine(TenantMixin, Base):
    __tablename__ = "return_lines"

    return_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sale_returns.id"), index=True)
    sale_line_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sale_lines.id"), index=True)
    qty: Mapped[Decimal] = mapped_column(Qty)
    refund: Mapped[int]
    cogs_reversed: Mapped[int]
