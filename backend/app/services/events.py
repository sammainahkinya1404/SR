"""In-process domain events (spec Part B §3). Handlers run synchronously inside the posting's
transaction, so a failing handler rolls the posting back. Alerts and metric updates (phase 5)
subscribe here."""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class StockReceived:
    business_id: UUID
    batch_id: UUID
    product_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class PriceChanged:
    business_id: UUID
    product_id: UUID
    old_price: int
    new_price: int


@dataclass(frozen=True)
class SalePosted:
    business_id: UUID
    sale_id: UUID
    total: int


@dataclass(frozen=True)
class SaleReturned:
    business_id: UUID
    sale_id: UUID
    return_id: UUID
    refund_total: int


type Handler = Callable[[Session, object], None]
_handlers: dict[type, list[Handler]] = defaultdict(list)


def subscribe(event_type: type, handler: Handler) -> None:
    _handlers[event_type].append(handler)


def publish(session: Session, event: object) -> None:
    for handler in _handlers[type(event)]:
        handler(session, event)
