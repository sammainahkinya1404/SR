from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import Ctx
from app.domain.landed_cost import SharedCostType
from app.schemas.stock_in import BatchCreate, BatchOut, CostSet
from app.services import stock_in
from app.services.actor import require_owner
from app.services.stock_in import BatchStatus

router = APIRouter(prefix="/stock-in-batches", tags=["stock-in"])


@router.post("", status_code=201, response_model=BatchOut)
def create_batch(data: BatchCreate, ctx: Ctx):
    return stock_in.to_out(stock_in.create_batch(ctx.session, ctx.actor, ctx.business, data))


@router.get("", response_model=list[BatchOut])
def list_batches(
    ctx: Ctx, status: BatchStatus | None = None, limit: int = Query(default=50, ge=1, le=500)
):
    """Recent deliveries, newest first; `status=draft` finds unposted ones."""
    require_owner(ctx.actor, "view deliveries")
    return [stock_in.to_out(b) for b in stock_in.list_batches(ctx.session, status, limit)]


@router.get("/{batch_id}", response_model=BatchOut)
def get_batch(batch_id: UUID, ctx: Ctx):
    return stock_in.to_out(stock_in.get_batch(ctx.session, batch_id))


@router.put("/{batch_id}/costs/{cost_type}", response_model=BatchOut)
def set_cost(batch_id: UUID, cost_type: SharedCostType, data: CostSet, ctx: Ctx):
    batch = stock_in.set_cost(ctx.session, ctx.actor, batch_id, cost_type, data.amount_cents)
    return stock_in.to_out(batch)


@router.post("/{batch_id}/post", response_model=BatchOut)
def post_batch(batch_id: UUID, ctx: Ctx):
    return stock_in.to_out(stock_in.post_batch(ctx.session, ctx.actor, ctx.business, batch_id))


@router.post("/{batch_id}/void", response_model=BatchOut)
def void_batch(batch_id: UUID, ctx: Ctx):
    return stock_in.to_out(stock_in.void_batch(ctx.session, ctx.actor, batch_id))
