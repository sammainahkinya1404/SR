from fastapi import APIRouter

from app.api.deps import Ctx
from app.schemas.inventory import ReceiveCreate, ReceiveOut
from app.services import inventory

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.post("/receive", status_code=201, response_model=ReceiveOut)
def receive_stock(data: ReceiveCreate, ctx: Ctx):
    """Add stock: one item, or a bulk order sharing one transport payment. New names become new
    products, priced by the pricing engine from their landed cost."""
    return inventory.receive(ctx.session, ctx.actor, ctx.business, data)
