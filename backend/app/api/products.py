from uuid import UUID

from fastapi import APIRouter

from app.api.deps import Ctx
from app.domain.pricing import PricingMode
from app.schemas.products import (
    MinPricesUpdate,
    MovementOut,
    PriceHistoryOut,
    PricingUpdate,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from app.services import pricing, products

router = APIRouter(prefix="/products", tags=["products"])


def _out(ctx: Ctx, product) -> ProductOut:
    qty = products.qty_on_hand(ctx.session, [product.id])[product.id]
    return products.to_out(product, qty, ctx.business)


@router.get("", response_model=list[ProductOut])
def list_products(ctx: Ctx, include_inactive: bool = False):
    items = products.list_products(ctx.session, include_inactive)
    qty = products.qty_on_hand(ctx.session, [p.id for p in items])
    return [products.to_out(p, qty[p.id], ctx.business) for p in items]


@router.post("", status_code=201, response_model=ProductOut)
def create_product(data: ProductCreate, ctx: Ctx):
    return _out(ctx, products.create_product(ctx.session, ctx.actor, data))


@router.put("/min-prices", response_model=list[ProductOut])
def set_min_prices(data: MinPricesUpdate, ctx: Ctx):
    """Set the bottom of each item's price range (many at once). Cashiers can sell anywhere from
    the minimum up to the selling price; below it needs the owner."""
    changed = pricing.set_min_prices(
        ctx.session, ctx.actor, [(i.product_id, i.min_price_cents) for i in data.items]
    )
    qty = products.qty_on_hand(ctx.session, [p.id for p in changed])
    return [products.to_out(p, qty[p.id], ctx.business) for p in changed]


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: UUID, ctx: Ctx):
    return _out(ctx, products.get_product(ctx.session, product_id))


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(product_id: UUID, data: ProductUpdate, ctx: Ctx):
    return _out(ctx, products.update_product(ctx.session, ctx.actor, product_id, data))


@router.put("/{product_id}/pricing", response_model=ProductOut)
def set_pricing(product_id: UUID, data: PricingUpdate, ctx: Ctx):
    product = products.get_product(ctx.session, product_id, lock=True)
    pricing.set_pricing(
        ctx.session,
        ctx.actor,
        ctx.business,
        product,
        PricingMode(data.pricing_mode),
        data.target_value,
        data.price_cents,
        data.reason,
    )
    return _out(ctx, product)


@router.get("/{product_id}/movements", response_model=list[MovementOut])
def list_movements(product_id: UUID, ctx: Ctx):
    return products.list_movements(ctx.session, product_id)


@router.get("/{product_id}/price-history", response_model=list[PriceHistoryOut])
def list_price_history(product_id: UUID, ctx: Ctx):
    return products.list_price_history(ctx.session, product_id)
