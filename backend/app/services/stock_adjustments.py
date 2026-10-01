"""Stock leaving without a sale (spec Part A §2, §7): damage and theft are posted as expenses
automatically; stock the owner takes for personal use is a drawing, never an expense."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.domain import inventory
from app.domain.clock import business_today
from app.domain.inventory import MovementType
from app.models import Expense, StockMovement
from app.schemas.finance import StockAdjustmentCreate
from app.services import expenses, owner
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, RuleViolation
from app.services.products import get_product, qty_on_hand


@dataclass(frozen=True)
class AdjustmentResult:
    movement: StockMovement
    value: int  # qty x WAC
    expense: Expense | None
    drawing: owner.DrawingResult | None


def write_off(session: Session, actor: Actor, data: StockAdjustmentCreate) -> AdjustmentResult:
    require_owner(actor, "write off stock")
    if session.get(StockMovement, data.id) is not None:
        raise Conflict("stock adjustment already exists")
    product = get_product(session, data.product_id, lock=True)
    on_hand = qty_on_hand(session, [product.id])[product.id]
    if data.qty > on_hand:
        raise RuleViolation(f"only {on_hand} {product.uom} of {product.sku} on hand")

    value = inventory.stock_value(data.qty, product.wac)
    movement = StockMovement(
        id=data.id,
        business_id=actor.business_id,
        product_id=product.id,
        type=MovementType(data.type),
        qty=-data.qty,
        unit_cost=product.wac,
        wac_snapshot=product.wac,
        reason=data.reason,
        user_id=actor.user_id,
    )
    note = f"{data.qty} {product.uom} {product.name}: {data.reason}"
    expense = drawing = None
    if data.type == MovementType.OWNER_CONSUMPTION:
        drawing = owner.record_stock_drawing(session, actor, value, note)
        movement.ref_type, movement.ref_id = "owner_entry", drawing.entry.id
    else:
        expense = expenses.post_expense(
            session,
            actor,
            date=business_today(),
            category=expenses.category_named(session, expenses.STOCK_LOSS),
            amount=value,
            account_id=None,  # the money was spent when the stock was bought
            note=note,
            source=expenses.ExpenseSource.STOCK_LOSS,
            ref_type="stock_movement",
            ref_id=movement.id,
        )
        movement.ref_type, movement.ref_id = "expense", expense.id
    session.add(movement)
    session.flush()
    return AdjustmentResult(movement, value, expense, drawing)
