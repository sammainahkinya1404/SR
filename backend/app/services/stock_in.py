"""Stock-in batches with landed cost (spec Part A §3, Part B §5 'Stock-in posting')."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import inventory
from app.domain.landed_cost import (
    AllocationMethod,
    LineInput,
    SharedCostType,
    allocate_shared_costs,
    landed_unit_cost,
    missing_cost_types,
)
from app.models import BatchCost, Business, Product, StockInBatch, StockInLine, StockMovement
from app.schemas.stock_in import BatchCreate, BatchOut, LineOut
from app.services import audit, events
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, NotFound, RuleViolation
from app.services.pricing import propose_reprice
from app.services.products import qty_on_hand


class BatchStatus(StrEnum):
    DRAFT = "draft"
    POSTED = "posted"
    VOIDED = "voided"


def get_batch(session: Session, batch_id: UUID, *, lock: bool = False) -> StockInBatch:
    batch = session.get(StockInBatch, batch_id, with_for_update=lock)
    if batch is None:
        raise NotFound("stock-in batch not found")
    return batch


def list_batches(session: Session, status: BatchStatus | None, limit: int) -> list[StockInBatch]:
    stmt = (
        select(StockInBatch)
        .order_by(StockInBatch.date.desc(), StockInBatch.created_at.desc())
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(StockInBatch.status == status)
    return list(session.scalars(stmt))


def _require_draft(batch: StockInBatch) -> None:
    if batch.status != BatchStatus.DRAFT:
        raise Conflict(f"batch is {batch.status}")


def create_batch(
    session: Session, actor: Actor, business: Business, data: BatchCreate
) -> StockInBatch:
    require_owner(actor, "receive stock")
    if session.get(StockInBatch, data.id) is not None:
        raise Conflict("batch already exists")
    product_ids = {line.product_id for line in data.lines}
    found = set(session.scalars(select(Product.id).where(Product.id.in_(product_ids))))
    if unknown := product_ids - found:
        raise NotFound(f"unknown products: {sorted(map(str, unknown))}")

    batch = StockInBatch(
        id=data.id,
        business_id=actor.business_id,
        supplier_name=data.supplier_name,
        date=data.date,
        allocation_method=data.allocation_method or business.default_allocation_method,
        status=BatchStatus.DRAFT,
        created_by=actor.user_id,
    )
    session.add(batch)
    session.flush()
    for position, line in enumerate(data.lines):
        session.add(
            StockInLine(
                id=line.id,
                business_id=actor.business_id,
                batch_id=batch.id,
                position=position,
                product_id=line.product_id,
                qty=line.qty,
                bp=line.bp_cents,
            )
        )
    for cost_type, amount in data.costs.items():
        session.add(
            BatchCost(
                business_id=actor.business_id, batch_id=batch.id, type=cost_type, amount=amount
            )
        )
    session.flush()
    session.refresh(batch)
    return batch


def set_cost(
    session: Session, actor: Actor, batch_id: UUID, cost_type: SharedCostType, amount: int
) -> StockInBatch:
    require_owner(actor, "edit stock-in costs")
    batch = get_batch(session, batch_id, lock=True)
    _require_draft(batch)
    existing = next((c for c in batch.costs if c.type == cost_type), None)
    if existing is None:
        batch.costs.append(
            BatchCost(
                business_id=actor.business_id, batch_id=batch.id, type=cost_type, amount=amount
            )
        )
    else:
        existing.amount = amount
    session.flush()
    return batch


def void_batch(session: Session, actor: Actor, batch_id: UUID) -> StockInBatch:
    """Drafts are abandoned by voiding, never deleted."""
    require_owner(actor, "void stock-in batches")
    batch = get_batch(session, batch_id, lock=True)
    _require_draft(batch)
    batch.status = BatchStatus.VOIDED
    return batch


def post_batch(session: Session, actor: Actor, business: Business, batch_id: UUID) -> StockInBatch:
    require_owner(actor, "post stock-in batches")
    batch = get_batch(session, batch_id, lock=True)
    _require_draft(batch)

    # 1. Every shared cost must be entered or explicitly zero.
    if missing := missing_cost_types({c.type for c in batch.costs}):
        raise RuleViolation(f"enter or zero these shared costs first: {[m.value for m in missing]}")

    # 2-3. Allocate shared costs and compute landed unit cost per line.
    allocations = allocate_shared_costs(
        [LineInput(qty=line.qty, bp=line.bp) for line in batch.lines],
        sum(c.amount for c in batch.costs),
        AllocationMethod(batch.allocation_method),
    )

    # Lock the products in a fixed order, then read quantities from the ledger. SQLite ignores
    # FOR UPDATE (BEGIN IMMEDIATE in db.py serializes writers instead); on Postgres it is the lock.
    product_ids = sorted({line.product_id for line in batch.lines})
    products = {
        p.id: p
        for p in session.scalars(
            select(Product)
            .where(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
        )
    }
    qty = qty_on_hand(session, product_ids)
    starting_wac = {pid: products[pid].wac for pid in product_ids}

    # 4-5. Stock movements and WAC, line by line (a product may appear on several lines).
    for line, allocated in zip(batch.lines, allocations, strict=True):
        landed = landed_unit_cost(line.qty, line.bp, allocated)
        line.allocated_cost = allocated
        line.landed_unit_cost = landed
        product = products[line.product_id]
        product.wac = inventory.new_wac(qty[product.id], product.wac, line.qty, landed)
        qty[product.id] += line.qty
        session.add(
            StockMovement(
                business_id=actor.business_id,
                product_id=product.id,
                type=inventory.MovementType.PURCHASE,
                qty=line.qty,
                unit_cost=landed,
                wac_snapshot=product.wac,
                ref_type="stock_in_batch",
                ref_id=batch.id,
                user_id=actor.user_id,
            )
        )

    # 6. Audit cost changes and raise price suggestions where WAC moved past the threshold.
    for pid in product_ids:
        product = products[pid]
        if product.wac != starting_wac[pid]:
            audit.record(session, actor, "product", pid, "wac", starting_wac[pid], product.wac)
            propose_reprice(session, business, product, starting_wac[pid])

    batch.status = BatchStatus.POSTED
    batch.posted_by = actor.user_id
    batch.posted_at = datetime.now(UTC)
    session.flush()
    events.publish(session, events.StockReceived(actor.business_id, batch.id, tuple(product_ids)))
    return batch


def to_out(batch: StockInBatch) -> BatchOut:
    costs = {SharedCostType(c.type): c.amount for c in batch.costs}
    return BatchOut(
        id=batch.id,
        supplier_name=batch.supplier_name,
        date=batch.date,
        allocation_method=AllocationMethod(batch.allocation_method),
        status=batch.status,
        lines=[
            LineOut(
                id=line.id,
                product_id=line.product_id,
                qty=line.qty,
                bp_cents=line.bp,
                allocated_cost_cents=line.allocated_cost,
                landed_unit_cost_cents=line.landed_unit_cost,
            )
            for line in batch.lines
        ],
        costs=costs,
        missing_costs=missing_cost_types(set(costs)),
    )
