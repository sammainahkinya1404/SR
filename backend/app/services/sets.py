"""Sets: bought as one unit, sold as separate items (owner's feature; see domain/sets.py)."""

import uuid
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import inventory
from app.domain.inventory import MovementType
from app.domain.landed_cost import AllocationMethod, LineInput, allocate_shared_costs
from app.domain.money import to_cents
from app.domain.pricing import PricingMode
from app.models import Business, Product, ProductSet, SetComponent, StockMovement
from app.schemas.products import ProductCreate
from app.schemas.sets import ComponentOut, ConvertStockIn, SetOut, SetUpsert
from app.services import audit, pricing, products
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, NotFound, RuleViolation


def find_set_by_name(session: Session, name: str) -> ProductSet | None:
    return session.scalar(
        select(ProductSet).where(func.lower(func.trim(ProductSet.name)) == name.strip().lower())
    )


def get_set(session: Session, set_id: UUID) -> ProductSet:
    product_set = session.get(ProductSet, set_id)
    if product_set is None:
        raise NotFound("set not found")
    return product_set


def list_sets(session: Session) -> list[ProductSet]:
    return list(session.scalars(select(ProductSet).order_by(ProductSet.name)))


def upsert_set(
    session: Session, actor: Actor, business: Business, data: SetUpsert, set_id: UUID | None = None
) -> ProductSet:
    """Create or redefine a set: its name, and each component with its qty per set and price."""
    require_owner(actor, "manage sets")
    name = data.name.strip()
    same_name = find_set_by_name(session, name)
    if set_id is None:
        if session.get(ProductSet, data.id) is not None:
            raise Conflict("set already exists")
        if same_name is not None:
            raise Conflict(f"a set named {same_name.name!r} already exists")
        product_set = ProductSet(id=data.id, business_id=actor.business_id, name=name, active=True)
        session.add(product_set)
    else:
        product_set = get_set(session, set_id)
        if same_name is not None and same_name.id != product_set.id:
            raise Conflict(f"a set named {same_name.name!r} already exists")
        product_set.name = name
    # Stock is added by name, so a set and an item can't share one.
    if products.find_by_name(session, name) is not None:
        raise Conflict(f"an item is already called {name!r}: give the set a different name")
    product_set.category = (data.category or "").strip() or None
    session.flush()

    rows = {
        r.product_id: r
        for r in session.scalars(select(SetComponent).where(SetComponent.set_id == product_set.id))
    }
    kept: set[UUID] = set()
    for position, component in enumerate(data.components):
        if component.product_id is not None:
            product = products.get_product(session, component.product_id)
        elif (product := products.find_by_name(session, component.name)) is None:
            product = products.create_product(
                session,
                actor,
                ProductCreate(
                    name=component.name,
                    category=product_set.category,
                    pricing_mode=PricingMode.MANUAL,
                    price_cents=component.price_cents,
                ),
            )
        if product.id in kept:
            raise RuleViolation(f"{product.name} is listed twice")
        kept.add(product.id)

        row = rows.get(product.id) or session.scalar(
            select(SetComponent).where(SetComponent.product_id == product.id)
        )
        if row is not None and row.active and row.set_id != product_set.id:
            other = session.get(ProductSet, row.set_id)
            raise Conflict(f"{product.name} is already in the set {other.name!r}")
        if row is None:
            row = SetComponent(business_id=actor.business_id, product_id=product.id)
            session.add(row)
        row.set_id = product_set.id
        row.qty = component.qty_per_set
        row.position = position
        row.active = True
        if product.category is None and product_set.category:
            product.category = product_set.category
        # Components are priced by the owner; the set's cost is then shared by these prices.
        if product.pricing_mode != PricingMode.MANUAL or product.price != component.price_cents:
            pricing.set_pricing(
                session,
                actor,
                business,
                product,
                PricingMode.MANUAL,
                None,
                component.price_cents,
                f"price in set {name}",
            )
    for product_id, row in rows.items():
        if product_id not in kept:
            row.active = False
    session.flush()
    session.expire(product_set, ["components"])
    return product_set


def to_out(session: Session, product_set: ProductSet) -> SetOut:
    components = product_set.components
    items = {
        p.id: p
        for p in session.scalars(
            select(Product).where(Product.id.in_([c.product_id for c in components]))
        )
    }
    qty = products.qty_on_hand(session, list(items))
    value = sum(Decimal(items[c.product_id].price) * c.qty for c in components)
    return SetOut(
        id=product_set.id,
        name=product_set.name,
        category=product_set.category,
        active=product_set.active,
        set_value_cents=to_cents(value),
        components=[
            ComponentOut(
                product_id=c.product_id,
                name=items[c.product_id].name,
                qty_per_set=c.qty,
                price_cents=items[c.product_id].price,
                wac_cents=items[c.product_id].wac,
                qty_on_hand=qty[c.product_id],
                cost_share=(items[c.product_id].price * c.qty / value) if value else Decimal(0),
            )
            for c in components
        ],
    )


def convert_stock(
    session: Session, actor: Actor, set_id: UUID, data: ConvertStockIn
) -> tuple[int, ProductSet]:
    """Move stock on hand into a set's components (e.g. the old 'Sufuria(1-5)' item into sizes
    1-5). The cost leaves the sources at their WAC and is re-shared across the targets by selling
    value, so the shop's total stock value is unchanged. Recorded as adjustment movements."""
    require_owner(actor, "move stock into a set")
    product_set = get_set(session, set_id)
    members = {c.product_id for c in product_set.components}
    source_ids = [s.product_id for s in data.sources]
    target_ids = [t.product_id for t in data.targets]
    if len(set(source_ids)) != len(source_ids) or len(set(target_ids)) != len(target_ids):
        raise RuleViolation("list each item once")
    if set(source_ids) & set(target_ids):
        raise RuleViolation("an item can't be both a source and a target")
    if not set(target_ids) <= members:
        raise RuleViolation(f"targets must be items in the set {product_set.name!r}")

    locked = {
        p.id: p
        for p in session.scalars(
            select(Product)
            .where(Product.id.in_(source_ids + target_ids))
            .order_by(Product.id)
            .with_for_update()
        )
    }
    if missing := set(source_ids + target_ids) - locked.keys():
        raise NotFound(f"unknown products: {sorted(map(str, missing))}")
    on_hand = products.qty_on_hand(session, list(locked))
    for s in data.sources:
        if s.qty > on_hand[s.product_id]:
            product = locked[s.product_id]
            raise RuleViolation(
                f"only {on_hand[s.product_id]} {product.uom} of {product.name} on hand"
            )
    if any(locked[t.product_id].price <= 0 for t in data.targets):
        raise RuleViolation("give every item in the set a selling price first")

    ref = uuid.uuid4()
    value = 0
    for s in data.sources:
        product = locked[s.product_id]
        value += to_cents(s.qty * product.wac)
        session.add(
            StockMovement(
                business_id=actor.business_id,
                product_id=product.id,
                type=MovementType.ADJUSTMENT,
                qty=-s.qty,
                unit_cost=product.wac,
                wac_snapshot=product.wac,
                ref_type="set_conversion",
                ref_id=ref,
                reason=data.reason,
                user_id=actor.user_id,
            )
        )
        if data.deactivate_emptied_sources and on_hand[product.id] == s.qty:
            product.active = False

    shares = allocate_shared_costs(
        [LineInput(qty=t.qty, bp=locked[t.product_id].price) for t in data.targets],
        value,
        AllocationMethod.BY_VALUE,
    )
    for t, share in zip(data.targets, shares, strict=True):
        product = locked[t.product_id]
        unit = to_cents(Decimal(share) / t.qty)
        old_wac = product.wac
        product.wac = inventory.new_wac(on_hand[product.id], product.wac, t.qty, unit)
        session.add(
            StockMovement(
                business_id=actor.business_id,
                product_id=product.id,
                type=MovementType.ADJUSTMENT,
                qty=t.qty,
                unit_cost=unit,
                wac_snapshot=product.wac,
                ref_type="set_conversion",
                ref_id=ref,
                reason=data.reason,
                user_id=actor.user_id,
            )
        )
        if product.wac != old_wac:
            audit.record(session, actor, "product", product.id, "wac", old_wac, product.wac)
    session.flush()
    return value, product_set


def reshare_cost(
    session: Session, actor: Actor, set_id: UUID, reason: str
) -> tuple[int, ProductSet]:
    """Re-share the cost of the set's stock on hand across its items by selling value.

    For stock recorded before its prices were set (e.g. a dinner set entered as 4 items at an equal
    cost): the total stays the same, each item's average cost is re-worked from its price. Recorded
    as a pair of adjustment movements per item (out at the old cost, in at the new), so the ledger
    replays to the new costs."""
    require_owner(actor, "re-share a set's stock cost")
    product_set = get_set(session, set_id)
    ids = [c.product_id for c in product_set.components]
    locked = {
        p.id: p
        for p in session.scalars(
            select(Product).where(Product.id.in_(ids)).order_by(Product.id).with_for_update()
        )
    }
    on_hand = products.qty_on_hand(session, ids)
    stocked = [pid for pid in ids if on_hand[pid] > 0]
    if not stocked:
        raise RuleViolation(f"no {product_set.name} items are in stock")
    if any(locked[pid].price <= 0 for pid in stocked):
        raise RuleViolation("give every item in the set a selling price first")

    value = sum(to_cents(on_hand[pid] * locked[pid].wac) for pid in stocked)
    shares = allocate_shared_costs(
        [LineInput(qty=on_hand[pid], bp=locked[pid].price) for pid in stocked],
        value,
        AllocationMethod.BY_VALUE,
    )
    ref = uuid.uuid4()
    for pid, share in zip(stocked, shares, strict=True):
        product = locked[pid]
        qty, old_wac = on_hand[pid], product.wac
        new_wac = to_cents(Decimal(share) / qty)
        if new_wac == old_wac:
            continue
        for moved, unit, after in ((-qty, old_wac, old_wac), (qty, new_wac, new_wac)):
            session.add(
                StockMovement(
                    business_id=actor.business_id,
                    product_id=pid,
                    type=MovementType.ADJUSTMENT,
                    qty=moved,
                    unit_cost=unit,
                    wac_snapshot=after,
                    ref_type="set_cost_reshare",
                    ref_id=ref,
                    reason=reason,
                    user_id=actor.user_id,
                )
            )
        product.wac = new_wac
        audit.record(session, actor, "product", pid, "wac", old_wac, new_wac)
    session.flush()
    return value, product_set
