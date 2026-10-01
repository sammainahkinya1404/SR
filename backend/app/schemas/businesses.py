from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field

from app.domain.landed_cost import AllocationMethod
from app.schemas.common import Schema
from app.services.actor import Role


class BusinessCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    owner_id: UUID = Field(default_factory=uuid4)
    owner_name: str = Field(min_length=1, max_length=200)
    owner_phone: str | None = None


class BusinessOut(Schema):
    id: UUID
    name: str
    owner_id: UUID


class UserCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = None
    role: Role


class UserOut(Schema):
    id: UUID
    name: str
    phone: str | None
    role: Role


class SetupUser(Schema):
    id: UUID
    name: str
    role: Role


class SetupOut(Schema):
    """What the sign-in screen needs before anyone is signed in."""

    configured: bool
    business_id: UUID | None
    business_name: str | None
    users: list[SetupUser]


class MeOut(Schema):
    user: UserOut
    business_id: UUID
    business_name: str


class SettingsOut(Schema):
    name: str
    price_rounding_cents: int
    price_floor_pct: Decimal
    reprice_threshold_pct: Decimal
    trading_days_per_month: int
    default_allocation_method: AllocationMethod
    default_target_margin: Decimal
    alert_low_cash_days: int
    alert_credit_risk_pct: Decimal
    alert_slow_moving_days: int
    alert_max_days_of_stock: int


class SettingsUpdate(Schema):
    """Fractions are 0-1 (0.10 = 10%), with at most 4 decimal places."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    price_rounding_cents: int | None = Field(default=None, ge=1)
    price_floor_pct: Decimal | None = Field(default=None, ge=0, le=10, decimal_places=4)
    reprice_threshold_pct: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=4)
    trading_days_per_month: int | None = Field(default=None, ge=1, le=31)
    default_allocation_method: AllocationMethod | None = None
    default_target_margin: Decimal | None = Field(default=None, ge=0, lt=1, decimal_places=4)
    alert_low_cash_days: int | None = Field(default=None, ge=0, le=365)
    alert_credit_risk_pct: Decimal | None = Field(default=None, ge=0, le=1, decimal_places=4)
    alert_slow_moving_days: int | None = Field(default=None, ge=1, le=365)
    alert_max_days_of_stock: int | None = Field(default=None, ge=1, le=3650)
