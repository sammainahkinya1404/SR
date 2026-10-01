import datetime as dt
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field

from app.domain.landed_cost import AllocationMethod, SharedCostType
from app.schemas.common import Cents, Schema


class LineIn(Schema):
    id: UUID = Field(default_factory=uuid4)
    product_id: UUID
    qty: Decimal = Field(gt=0, decimal_places=3)
    bp_cents: Cents


class BatchCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    supplier_name: str | None = None
    date: dt.date
    allocation_method: AllocationMethod | None = None  # defaults to the business setting
    lines: list[LineIn] = Field(min_length=1)
    # Enter 0 to mark a cost type as explicitly zero. Omitted types block posting.
    costs: dict[SharedCostType, Cents] = Field(default_factory=dict)


class CostSet(Schema):
    amount_cents: Cents


class LineOut(Schema):
    id: UUID
    product_id: UUID
    qty: Decimal
    bp_cents: int
    allocated_cost_cents: int | None
    landed_unit_cost_cents: int | None


class BatchOut(Schema):
    id: UUID
    supplier_name: str | None
    date: dt.date
    allocation_method: AllocationMethod
    status: str
    lines: list[LineOut]
    costs: dict[SharedCostType, int]
    missing_costs: list[SharedCostType]
