import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, created_at_column
from app.models.types import Fraction


class Business(IdMixin, Base):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200))
    # Settings (spec Part B §4). Money is integer cents.
    price_rounding: Mapped[int] = mapped_column(default=500)  # prices round up to this: 500 = KSh 5
    price_floor_pct: Mapped[Decimal] = mapped_column(Fraction, default=Decimal("0.10"))
    reprice_threshold_pct: Mapped[Decimal] = mapped_column(Fraction, default=Decimal("0.05"))
    trading_days_per_month: Mapped[int] = mapped_column(Integer, default=26)
    default_allocation_method: Mapped[str] = mapped_column(String(20), default="by_value")
    # Receipt numbers are sequential per business; incremented inside the sale transaction.
    next_receipt_no: Mapped[int] = mapped_column(default=1)
    # Alert thresholds (the "X" values in spec Part A §10).
    default_target_margin: Mapped[Decimal] = mapped_column(Fraction, default=Decimal("0.20"))
    alert_low_cash_days: Mapped[int] = mapped_column(Integer, default=7)
    alert_credit_risk_pct: Mapped[Decimal] = mapped_column(Fraction, default=Decimal("0.10"))
    alert_slow_moving_days: Mapped[int] = mapped_column(Integer, default=30)
    alert_max_days_of_stock: Mapped[int] = mapped_column(Integer, default=90)
    created_at: Mapped[datetime] = created_at_column()


class User(TenantMixin, Base):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(20))  # Role
    pin_hash: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = created_at_column()


class AuditLog(TenantMixin, Base):
    """Append-only (enforced by a DB trigger)."""

    __tablename__ = "audit_log"

    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID]
    field: Mapped[str] = mapped_column(String(50))
    old: Mapped[str | None] = mapped_column(Text)
    new: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()
