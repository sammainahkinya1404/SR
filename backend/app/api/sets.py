from uuid import UUID

from fastapi import APIRouter

from app.api.deps import Ctx
from app.schemas.sets import (
    ConvertStockIn,
    ConvertStockOut,
    ReshareIn,
    ReshareOut,
    SetOut,
    SetUpsert,
)
from app.services import sets

router = APIRouter(prefix="/sets", tags=["sets"])


@router.get("", response_model=list[SetOut])
def list_sets(ctx: Ctx):
    return [sets.to_out(ctx.session, s) for s in sets.list_sets(ctx.session)]


@router.post("", status_code=201, response_model=SetOut)
def create_set(data: SetUpsert, ctx: Ctx):
    """A set bought as one unit and sold as separate items, each with its own price."""
    return sets.to_out(ctx.session, sets.upsert_set(ctx.session, ctx.actor, ctx.business, data))


@router.get("/{set_id}", response_model=SetOut)
def get_set(set_id: UUID, ctx: Ctx):
    return sets.to_out(ctx.session, sets.get_set(ctx.session, set_id))


@router.put("/{set_id}", response_model=SetOut)
def update_set(set_id: UUID, data: SetUpsert, ctx: Ctx):
    """Redefine the set: name, components, qty per set and each component's price."""
    product_set = sets.upsert_set(ctx.session, ctx.actor, ctx.business, data, set_id)
    return sets.to_out(ctx.session, product_set)


@router.post("/{set_id}/convert-stock", response_model=ConvertStockOut)
def convert_stock(set_id: UUID, data: ConvertStockIn, ctx: Ctx):
    """Move stock already on hand into this set's items, keeping its total cost."""
    value, product_set = sets.convert_stock(ctx.session, ctx.actor, set_id, data)
    return ConvertStockOut(value_moved_cents=value, set=sets.to_out(ctx.session, product_set))


@router.post("/{set_id}/reshare-cost", response_model=ReshareOut)
def reshare_cost(set_id: UUID, data: ReshareIn, ctx: Ctx):
    """Re-share the cost of the set's stock on hand across its items by selling price."""
    value, product_set = sets.reshare_cost(ctx.session, ctx.actor, set_id, data.reason)
    return ReshareOut(value_cents=value, set=sets.to_out(ctx.session, product_set))
