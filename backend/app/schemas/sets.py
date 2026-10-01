from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from app.schemas.common import Cents, Schema


class ComponentIn(Schema):
    """An existing item (product_id) or a new one (name). The price is its own selling price."""

    product_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    qty_per_set: Decimal = Field(gt=0, decimal_places=3)
    price_cents: Cents = Field(gt=0)

    @model_validator(mode="after")
    def _product_or_name(self):
        if self.product_id is None and not (self.name or "").strip():
            raise ValueError("give a product_id or a name")
        return self


class SetUpsert(Schema):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    components: list[ComponentIn] = Field(min_length=1)


class ComponentOut(Schema):
    product_id: UUID
    name: str
    qty_per_set: Decimal
    price_cents: int
    wac_cents: int
    qty_on_hand: Decimal
    # Share of the set's cost this component carries (price x qty / set value).
    cost_share: Decimal


class SetOut(Schema):
    id: UUID
    name: str
    category: str | None
    active: bool
    set_value_cents: int  # selling one full set, piece by piece
    components: list[ComponentOut]


class StockQty(Schema):
    product_id: UUID
    qty: Decimal = Field(gt=0, decimal_places=3)


class ConvertStockIn(Schema):
    """Move stock already on hand (e.g. an old 'Sufuria(1-5)' item) into a set's components. The
    total cost moves with it, re-shared across the components by selling price."""

    sources: list[StockQty] = Field(min_length=1)
    targets: list[StockQty] = Field(min_length=1)
    reason: str = Field(min_length=1)
    # Deactivate source items left with no stock, so they stop showing at the till.
    deactivate_emptied_sources: bool = True


class ConvertStockOut(Schema):
    value_moved_cents: int
    set: SetOut


class ReshareIn(Schema):
    reason: str = Field(min_length=1)


class ReshareOut(Schema):
    """The set's stock on hand keeps its total cost, re-shared across the items by price."""

    value_cents: int
    set: SetOut
