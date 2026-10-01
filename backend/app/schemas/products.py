from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from pydantic import Field

from app.domain.pricing import PricingMode
from app.schemas.common import Cents, Schema


class ProductCreate(Schema):
    id: UUID = Field(default_factory=uuid4)
    # SKU or barcode; generated (ITEM-0001, ...) when left out.
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    category: str | None = None
    uom: str = "pcs"
    supplier_name: str | None = None
    # Starting price. A rule-based mode can only price once a cost is known, which happens on the
    # first stock-in: that posting raises a price suggestion for the owner to approve.
    price_cents: Cents = 0
    pricing_mode: PricingMode = PricingMode.MANUAL
    target_value: Decimal | None = Field(default=None, ge=0, decimal_places=4)
    reorder_point: Decimal = Field(default=Decimal(0), ge=0, decimal_places=3)
    lead_time_days: int = Field(default=0, ge=0)


class ProductUpdate(Schema):
    """Descriptive fields only. Price goes through PUT /products/{id}/pricing; cost only changes
    through stock postings."""

    sku: str | None = Field(default=None, min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = None
    uom: str | None = None
    supplier_name: str | None = None
    reorder_point: Decimal | None = Field(default=None, ge=0, decimal_places=3)
    lead_time_days: int | None = Field(default=None, ge=0)
    active: bool | None = None


class PricingUpdate(Schema):
    pricing_mode: PricingMode
    target_value: Decimal | None = Field(default=None, ge=0, decimal_places=4)
    # Required for manual mode; ignored for rule-based modes, whose price is derived from WAC.
    price_cents: Cents | None = None
    reason: str = Field(min_length=1)


class MinPriceItem(Schema):
    product_id: UUID
    # KSh cents; null clears it so the automatic floor (cost + floor %) applies again.
    min_price_cents: Cents | None


class MinPricesUpdate(Schema):
    items: list[MinPriceItem] = Field(min_length=1)


class ProductOut(Schema):
    id: UUID
    sku: str
    name: str
    category: str | None
    uom: str
    supplier_name: str | None
    active: bool
    pricing_mode: PricingMode
    target_value: Decimal | None
    price_cents: int
    wac_cents: int
    qty_on_hand: Decimal
    stock_value_cents: int
    # Always shown side by side, both from WAC (spec Part A §4). None when undefined.
    margin: Decimal | None
    markup: Decimal | None
    # The price range: from floor_price_cents (the owner's min_price_cents when set, else the
    # automatic cost + floor %) up to price_cents.
    min_price_cents: int | None
    auto_floor_price_cents: int  # what the minimum would be without min_price_cents
    floor_price_cents: int
    below_floor: bool
    reorder_point: Decimal
    lead_time_days: int


class MovementOut(Schema):
    id: UUID
    type: str
    qty: Decimal
    unit_cost: int
    wac_snapshot: int
    ref_type: str | None
    ref_id: UUID | None
    reason: str | None
    user_id: UUID
    ts: datetime


class PriceHistoryOut(Schema):
    old_price: int
    new_price: int
    reason: str
    user_id: UUID
    ts: datetime


class SuggestionOut(Schema):
    id: UUID
    product_id: UUID
    suggested_price: int
    price_at_suggestion: int
    previous_wac: int
    trigger_wac: int
    status: str
    created_at: datetime
