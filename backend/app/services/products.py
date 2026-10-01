from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import inventory, pricing
from app.models import Business, PriceHistory, Product, ProductSet, StockMovement
from app.schemas.products import ProductCreate, ProductOut, ProductUpdate
from app.services import audit
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, NotFound


def qty_on_hand(session: Session, product_ids: list[UUID]) -> dict[UUID, Decimal]:
    """Quantity on hand is always derived from the stock ledger (spec Part A §2)."""
    rows = session.execute(
        select(StockMovement.product_id, func.sum(StockMovement.qty))
        .where(StockMovement.product_id.in_(product_ids))
        .group_by(StockMovement.product_id)
    )
    qty = {pid: Decimal("0.000") for pid in product_ids}  # same scale as stored quantities
    qty.update({pid: total for pid, total in rows})
    return qty


def get_product(session: Session, product_id: UUID, *, lock: bool = False) -> Product:
    product = session.get(Product, product_id, with_for_update=lock)
    if product is None:
        raise NotFound("product not found")
    return product


def list_products(session: Session, include_inactive: bool) -> list[Product]:
    stmt = select(Product).order_by(Product.name)
    if not include_inactive:
        stmt = stmt.where(Product.active)
    return list(session.scalars(stmt))


def _ensure_sku_free(session: Session, sku: str, exclude_id: UUID | None = None) -> None:
    stmt = select(Product.id).where(Product.sku == sku)
    if exclude_id is not None:
        stmt = stmt.where(Product.id != exclude_id)
    if session.scalar(stmt) is not None:
        raise Conflict(f"SKU {sku!r} is already in use")


def find_by_name(session: Session, name: str) -> Product | None:
    """Stock is added by name, so names are unique in the shop (ignoring case and spacing)."""
    return session.scalar(
        select(Product).where(func.lower(func.trim(Product.name)) == name.strip().lower())
    )


def _ensure_name_free(session: Session, name: str, exclude_id: UUID | None = None) -> None:
    existing = find_by_name(session, name)
    if existing is not None and existing.id != exclude_id:
        raise Conflict(f"a product named {existing.name!r} already exists")
    # Stock is added by name, so an item can't share a name with a set either.
    same_set = session.scalar(
        select(ProductSet.name).where(
            func.lower(func.trim(ProductSet.name)) == name.strip().lower()
        )
    )
    if same_set is not None:
        raise Conflict(f"a set is already called {same_set!r}")


def next_sku(session: Session) -> str:
    """ITEM-0001, ITEM-0002, ...: a placeholder until a barcode is recorded."""
    n = session.scalar(select(func.count()).select_from(Product)) + 1
    while True:
        sku = f"ITEM-{n:04d}"
        if session.scalar(select(Product.id).where(Product.sku == sku)) is None:
            return sku
        n += 1


def create_product(session: Session, actor: Actor, data: ProductCreate) -> Product:
    require_owner(actor, "create products")
    if session.get(Product, data.id) is not None:
        raise Conflict("product already exists")
    _ensure_name_free(session, data.name)
    sku = data.sku or next_sku(session)
    _ensure_sku_free(session, sku)
    product = Product(
        id=data.id,
        business_id=actor.business_id,
        sku=sku,
        name=data.name.strip(),
        category=data.category,
        uom=data.uom,
        supplier_name=data.supplier_name,
        wac=0,
        price=data.price_cents,
        pricing_mode=data.pricing_mode,
        target_value=data.target_value,
        reorder_point=data.reorder_point,
        lead_time_days=data.lead_time_days,
        active=True,
    )
    session.add(product)
    session.flush()
    if data.price_cents:
        session.add(
            PriceHistory(
                business_id=actor.business_id,
                product_id=product.id,
                old_price=0,
                new_price=data.price_cents,
                reason="initial price",
                user_id=actor.user_id,
            )
        )
        audit.record(session, actor, "product", product.id, "price", 0, data.price_cents)
    return product


def update_product(
    session: Session, actor: Actor, product_id: UUID, data: ProductUpdate
) -> Product:
    require_owner(actor, "edit products")
    product = get_product(session, product_id, lock=True)
    changes = data.model_dump(exclude_unset=True)
    if changes.get("sku") not in (None, product.sku):
        _ensure_sku_free(session, changes["sku"], exclude_id=product.id)
    if changes.get("name") not in (None, product.name):
        _ensure_name_free(session, changes["name"], exclude_id=product.id)
    for field, value in changes.items():
        # Explicit null clears an optional field; required fields ignore null.
        if value is not None or field in _NULLABLE_FIELDS:
            setattr(product, field, value)
    return product


_NULLABLE_FIELDS = {"category", "supplier_name"}


def to_out(product: Product, qty: Decimal, business: Business) -> ProductOut:
    auto_floor = pricing.floor_price(product.wac, business.price_floor_pct)
    floor = product.min_price if product.min_price is not None else auto_floor
    return ProductOut(
        id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        uom=product.uom,
        supplier_name=product.supplier_name,
        active=product.active,
        pricing_mode=pricing.PricingMode(product.pricing_mode),
        target_value=product.target_value,
        price_cents=product.price,
        wac_cents=product.wac,
        qty_on_hand=qty,
        stock_value_cents=inventory.stock_value(qty, product.wac),
        margin=pricing.margin(product.price, product.wac),
        markup=pricing.markup(product.price, product.wac),
        min_price_cents=product.min_price,
        auto_floor_price_cents=auto_floor,
        floor_price_cents=floor,
        below_floor=product.price < floor,
        reorder_point=product.reorder_point,
        lead_time_days=product.lead_time_days,
    )


def list_movements(session: Session, product_id: UUID) -> list[StockMovement]:
    get_product(session, product_id)
    stmt = (
        select(StockMovement)
        .where(StockMovement.product_id == product_id)
        .order_by(StockMovement.ts, StockMovement.id)
    )
    return list(session.scalars(stmt))


def list_price_history(session: Session, product_id: UUID) -> list[PriceHistory]:
    get_product(session, product_id)
    stmt = (
        select(PriceHistory)
        .where(PriceHistory.product_id == product_id)
        .order_by(PriceHistory.ts, PriceHistory.id)
    )
    return list(session.scalars(stmt))
