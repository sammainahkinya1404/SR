import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, created_at_column
from app.models.types import Qty


class ProductSet(TenantMixin, Base):
    """A set bought as one unit (e.g. Sufuria 1-5) whose components are sold as separate items."""

    __tablename__ = "product_sets"
    __table_args__ = (UniqueConstraint("business_id", "name"),)

    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = created_at_column()

    components: Mapped[list["SetComponent"]] = relationship(
        order_by="SetComponent.position",
        primaryjoin="and_(ProductSet.id == SetComponent.set_id, SetComponent.active)",
        viewonly=True,
    )


class SetComponent(TenantMixin, Base):
    """What one set contains. A product belongs to at most one set; removing it from a set
    deactivates the row (nothing is deleted), and it can later join another set."""

    __tablename__ = "set_components"
    __table_args__ = (UniqueConstraint("business_id", "product_id"),)

    set_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("product_sets.id"), index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"))
    qty: Mapped[Decimal] = mapped_column(Qty)  # units per set
    position: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(default=True)
