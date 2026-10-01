import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, created_at_column


class PriceHistory(TenantMixin, Base):
    """Append-only (enforced by a DB trigger)."""

    __tablename__ = "price_history"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    old_price: Mapped[int]
    new_price: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    ts: Mapped[datetime] = created_at_column()


class PriceSuggestion(TenantMixin, Base):
    __tablename__ = "price_suggestions"

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    suggested_price: Mapped[int]
    price_at_suggestion: Mapped[int]
    previous_wac: Mapped[int]
    trigger_wac: Mapped[int]
    status: Mapped[str] = mapped_column(String(20), default="pending")  # SuggestionStatus
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = created_at_column()
