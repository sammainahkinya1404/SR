import datetime as dt
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, created_at_column
from app.models.types import Fraction, Qty


class Product(TenantMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("business_id", "sku"),)

    sku: Mapped[str] = mapped_column(String(64))  # SKU or barcode
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    uom: Mapped[str] = mapped_column(String(20), default="pcs")
    supplier_name: Mapped[str | None] = mapped_column(String(200))
    # wac and price are cached values; every change is audited. Quantity on hand is NOT stored:
    # it is always summed from stock_movements.
    wac: Mapped[int] = mapped_column(default=0)
    price: Mapped[int] = mapped_column(default=0)
    # Bottom of the item's price range, set by the owner: cashiers may sell anywhere from here up
    # to `price`. None = use the automatic floor (WAC + business.price_floor_pct).
    min_price: Mapped[int | None]
    pricing_mode: Mapped[str] = mapped_column(String(20), default="manual")  # PricingMode
    target_value: Mapped[Decimal | None] = mapped_column(Fraction)
    reorder_point: Mapped[Decimal] = mapped_column(Qty, default=Decimal(0))
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = created_at_column()


class StockMovement(TenantMixin, Base):
    """Append-only stock ledger (enforced by a DB trigger). qty is signed: stock-in is positive."""

    __tablename__ = "stock_movements"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))  # MovementType
    qty: Mapped[Decimal] = mapped_column(Qty)
    unit_cost: Mapped[int]
    wac_snapshot: Mapped[int]  # product WAC after this movement was posted
    ref_type: Mapped[str | None] = mapped_column(String(50))
    ref_id: Mapped[uuid.UUID | None]
    reason: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()


class StockInBatch(TenantMixin, Base):
    __tablename__ = "stock_in_batches"

    supplier_name: Mapped[str | None] = mapped_column(String(200))
    date: Mapped[dt.date]
    allocation_method: Mapped[str] = mapped_column(String(20))  # AllocationMethod
    status: Mapped[str] = mapped_column(String(20), default="draft")  # BatchStatus
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    posted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created_at_column()

    lines: Mapped[list["StockInLine"]] = relationship(order_by="StockInLine.position")
    costs: Mapped[list["BatchCost"]] = relationship()


class StockInLine(TenantMixin, Base):
    __tablename__ = "stock_in_lines"

    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_in_batches.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[Decimal] = mapped_column(Qty)
    bp: Mapped[int]  # buying price per unit
    # Filled in when the batch is posted.
    allocated_cost: Mapped[int | None]
    landed_unit_cost: Mapped[int | None]


class BatchCost(TenantMixin, Base):
    """One row per shared-cost type. No row means 'not entered yet'; 0 means explicitly zero."""

    __tablename__ = "batch_costs"
    __table_args__ = (UniqueConstraint("batch_id", "type"),)

    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stock_in_batches.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # SharedCostType
    amount: Mapped[int]
