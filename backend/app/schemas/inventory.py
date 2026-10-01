import datetime as dt
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from app.domain.landed_cost import AllocationMethod
from app.schemas.common import Cents, Schema


class ReceiveItem(Schema):
    """An existing product (by id), a set (by id), or a name. A name matching a set receives the
    set; a name not yet in the shop creates the product.

    For a set, qty is the number of sets and bp_cents the price paid per set: every component is
    stocked, with the set's cost shared across them by selling price."""

    product_id: UUID | None = None
    set_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)  # used when creating
    qty: Decimal = Field(gt=0, decimal_places=3)
    bp_cents: Cents  # buying price per unit (or per set)

    @model_validator(mode="after")
    def _product_or_name(self):
        if self.product_id is None and self.set_id is None and not (self.name or "").strip():
            raise ValueError("give a product_id, a set_id or a name")
        return self


class ReceiveCreate(Schema):
    """Stock arriving: one item, or a bulk order sharing one transport payment."""

    id: UUID = Field(default_factory=uuid4)  # client-generated: a retry cannot post twice
    date: dt.date | None = None  # defaults to today in Kenya
    items: list[ReceiveItem] = Field(min_length=1)
    transport_cents: Cents = 0
    # How transport is shared: by line value (BP x qty) or by quantity.
    allocation_method: AllocationMethod = AllocationMethod.BY_VALUE


class ReceivedLine(Schema):
    product_id: UUID
    name: str
    set_name: str | None  # the set this component came in
    category: str | None
    new_product: bool
    qty: Decimal
    bp_cents: int
    transport_share_cents: int
    landed_unit_cost_cents: int  # (BP x qty + transport share) / qty
    wac_cents: int  # the product's average cost after this delivery
    price_cents: int
    # "set": the pricing engine priced a new item; "suggested": cost moved, a new price awaits
    # approval; "unchanged": the current price stands.
    price_status: str


class ReceiveOut(Schema):
    id: UUID
    date: dt.date
    allocation_method: AllocationMethod
    goods_value_cents: int
    transport_cents: int
    lines: list[ReceivedLine]
