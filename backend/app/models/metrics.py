"""Metric snapshots and alerts (spec Part A §10, Part B §8)."""

import datetime as dt
import uuid
from datetime import datetime

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, created_at_column


class MetricSnapshot(TenantMixin, Base):
    """A cache of one business day's figures, rebuilt nightly from the ledgers (the source of
    truth). Recent days are recomputed each night so late or backdated postings are picked up."""

    __tablename__ = "metric_snapshots"
    __table_args__ = (UniqueConstraint("business_id", "date"),)

    date: Mapped[dt.date]
    sales: Mapped[int]
    cogs: Mapped[int]
    gross_profit: Mapped[int]
    opex: Mapped[int]
    net_profit: Mapped[int]
    stock_value: Mapped[int]  # at end of day
    cash: Mapped[int]  # all accounts, end of day
    computed_at: Mapped[datetime] = created_at_column()


class Alert(TenantMixin, Base):
    """At most one active (open or acknowledged) alert per type and entity. The checks resolve an
    alert when its condition clears; if it comes back later, a new alert is raised."""

    __tablename__ = "alerts"

    type: Mapped[str] = mapped_column(String(30))  # AlertType
    entity_id: Mapped[uuid.UUID | None]  # the product, for per-product alerts
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # AlertStatus
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = created_at_column()
    resolved_at: Mapped[datetime | None]
