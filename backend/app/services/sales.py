"""POS sales, payments and returns (spec Part A §5, Part B §5 'Sale posting')."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import inventory, pricing
from app.domain import sales as rules
from app.domain.receipts import ksh
from app.domain.sales import PaymentMethod
from app.models import (
    Business,
    Payment,
    Product,
    ReturnLine,
    Sale,
    SaleLine,
    SaleReturn,
    StockMovement,
)
from app.schemas.sales import ReturnCreate, SaleCreate
from app.services import audit, cash, credit, events, mpesa
from app.services.actor import Actor, Role, require_owner
from app.services.errors import Conflict, Forbidden, NotFound, RuleViolation
from app.services.pricing import propose_reprice
from app.services.products import qty_on_hand


@dataclass(frozen=True)
class Returned:
    qty: Decimal = Decimal(0)
    refund: int = 0
    cogs: int = 0


def _lock_products(session: Session, product_ids: set[UUID]) -> dict[UUID, Product]:
    # Fixed lock order avoids deadlocks on Postgres; on SQLite BEGIN IMMEDIATE serializes writers.
    products = {
        p.id: p
        for p in session.scalars(
            select(Product)
            .where(Product.id.in_(product_ids))
            .order_by(Product.id)
            .with_for_update()
        )
    }
    if missing := product_ids - products.keys():
        raise NotFound(f"unknown products: {sorted(map(str, missing))}")
    return products


def post_sale(
    session: Session, actor: Actor, business: Business, data: SaleCreate
) -> tuple[Sale, bool]:
    """Post a sale. Returns (sale, created); replaying a known sale id returns it unchanged."""
    if (existing := session.get(Sale, data.id)) is not None:
        return existing, False

    products = _lock_products(session, {line.product_id for line in data.lines})
    if inactive := [p.sku for p in products.values() if not p.active]:
        raise RuleViolation(f"inactive products cannot be sold: {inactive}")

    # Online sales cannot take stock below zero (offline oversells are phase 6).
    wanted: dict[UUID, Decimal] = defaultdict(Decimal)
    for line in data.lines:
        wanted[line.product_id] += line.qty
    on_hand = qty_on_hand(session, list(wanted))
    if short := [
        f"{products[pid].sku} (have {on_hand[pid]}, need {qty})"
        for pid, qty in wanted.items()
        if qty > on_hand[pid]
    ]:
        raise RuleViolation(f"not enough stock: {', '.join(short)}")

    # 1. Price floor, and 2. WAC snapshot, COGS and gross profit per line.
    priced = []
    for line in data.lines:
        product = products[line.product_id]
        floor = pricing.effective_floor(product.min_price, product.wac, business.price_floor_pct)
        try:
            amounts = rules.line_amounts(line.qty, product.price, line.discount_cents, product.wac)
        except ValueError as e:
            raise RuleViolation(f"{product.sku}: {e}") from e
        override = rules.below_floor(amounts.net, line.qty, floor)
        priced.append((line, product, floor, amounts, override))

    if any(override for *_, override in priced):
        below = [f"{p.name} (min KSh {ksh(f)})" for _, p, f, _, o in priced if o]
        require_owner(actor, f"sell below the minimum price: {', '.join(below)}")
        if not (data.floor_override_reason or "").strip():
            raise RuleViolation("selling below the minimum price needs floor_override_reason")

    total = sum(a.net for _, _, _, a, _ in priced)

    tenders: list[tuple[PaymentMethod, int, str | None]] = []
    for p in data.payments:
        code = mpesa.normalize(p.mpesa_code) if p.method is PaymentMethod.MPESA else None
        if code is None and p.mpesa_code:
            raise RuleViolation("only M-Pesa payments take a transaction code")
        tenders.append((p.method, p.amount_cents, code))
    mpesa.ensure_unused(session, [c for *_, c in tenders if c])
    try:
        change = rules.settle(total, [(m, a) for m, a, _ in tenders])
    except ValueError as e:
        raise RuleViolation(str(e)) from e

    # 1b. Credit limit and overdue check (spec Part A §6); only the owner can override.
    customer = credit.get_customer(session, data.customer_id) if data.customer_id else None
    on_credit = sum(a for m, a, _ in tenders if m is PaymentMethod.CREDIT)
    credit_blocks: list[str] = []
    if on_credit:
        if customer is None:
            raise RuleViolation("a credit sale needs customer_id")
        if not customer.active:
            raise RuleViolation(f"{customer.name} is not an active credit customer")
        credit_blocks = credit.credit_sale_blocks(session, customer, on_credit)
        if credit_blocks:
            if actor.role is not Role.OWNER:
                raise Forbidden(
                    f"credit sale blocked ({'; '.join(credit_blocks)}): only the owner can override"
                )
            if not (data.credit_override_reason or "").strip():
                raise RuleViolation(
                    f"credit sale blocked ({'; '.join(credit_blocks)}): "
                    "overriding needs credit_override_reason"
                )

    session.refresh(business, with_for_update=True)
    receipt_no = business.next_receipt_no
    business.next_receipt_no = receipt_no + 1

    sale = Sale(
        id=data.id,
        business_id=actor.business_id,
        receipt_no=receipt_no,
        subtotal=sum(a.gross for _, _, _, a, _ in priced),
        discount_total=sum(line.discount_cents for line, *_ in priced),
        total=total,
        cogs=sum(a.cogs for _, _, _, a, _ in priced),
        gross_profit=sum(a.gross_profit for _, _, _, a, _ in priced),
        change_given=change,
        status="completed",
        device_id=data.device_id,
        customer_id=customer.id if customer else None,
        user_id=actor.user_id,
    )
    session.add(sale)
    session.flush()

    for position, (line, product, floor, amounts, override) in enumerate(priced):
        sale_line = SaleLine(
            business_id=actor.business_id,
            sale_id=sale.id,
            position=position,
            product_id=product.id,
            qty=line.qty,
            unit_price=product.price,
            discount=line.discount_cents,
            line_total=amounts.net,
            wac_snapshot=product.wac,
            cogs=amounts.cogs,
            gross_profit=amounts.gross_profit,
            floor_price=floor,
            floor_override=override,
        )
        session.add(sale_line)
        session.flush()
        # 3. Stock out at the current WAC (a sale never changes WAC).
        session.add(
            StockMovement(
                business_id=actor.business_id,
                product_id=product.id,
                type=inventory.MovementType.SALE,
                qty=-line.qty,
                unit_cost=product.wac,
                wac_snapshot=product.wac,
                ref_type="sale",
                ref_id=sale.id,
                user_id=actor.user_id,
            )
        )
        if override:
            audit.record(
                session,
                actor,
                "sale_line",
                sale_line.id,
                "below_floor_sale",
                f"floor {floor}/unit",
                f"{amounts.net} for {line.qty}: {data.floor_override_reason}",
            )

    # 4. Cash and M-Pesa settle into accounts (change comes out of the cash tendered); credit
    # goes to the customer's ledger as an invoice.
    by_method: dict[PaymentMethod, int] = defaultdict(int)
    for position, (method, amount, code) in enumerate(tenders):
        on_account = method is not PaymentMethod.CREDIT
        session.add(
            Payment(
                business_id=actor.business_id,
                sale_id=sale.id,
                position=position,
                method=method,
                amount=amount,
                mpesa_code=code,
                account_id=cash.account_for(session, method).id if on_account else None,
            )
        )
        by_method[method] += amount
    by_method[PaymentMethod.CASH] -= change
    if on_credit:
        credit.charge_sale(session, actor, customer, sale, by_method.pop(PaymentMethod.CREDIT))
        if credit_blocks:
            audit.record(
                session,
                actor,
                "sale",
                sale.id,
                "credit_override",
                "; ".join(credit_blocks),
                data.credit_override_reason,
            )
    for method, amount in by_method.items():
        account = cash.account_for(session, method)
        cash.post(session, actor, account, cash.CashEntryType.SALE, amount, "sale", sale.id)

    session.flush()
    session.refresh(sale)
    events.publish(session, events.SalePosted(actor.business_id, sale.id, sale.total))
    return sale, True


def get_sale(session: Session, sale_id: UUID) -> Sale:
    sale = session.get(Sale, sale_id)
    if sale is None:
        raise NotFound("sale not found")
    return sale


def list_sales(
    session: Session, since: datetime | None, until: datetime | None, limit: int
) -> list[Sale]:
    stmt = select(Sale).order_by(Sale.receipt_no.desc()).limit(limit)
    if since is not None:
        stmt = stmt.where(Sale.ts >= since)
    if until is not None:
        stmt = stmt.where(Sale.ts < until)
    return list(session.scalars(stmt))


def returned_by_line(session: Session, sale_line_ids: list[UUID]) -> dict[UUID, Returned]:
    rows = session.execute(
        select(
            ReturnLine.sale_line_id,
            func.sum(ReturnLine.qty),
            func.sum(ReturnLine.refund),
            func.sum(ReturnLine.cogs_reversed),
        )
        .where(ReturnLine.sale_line_id.in_(sale_line_ids))
        .group_by(ReturnLine.sale_line_id)
    )
    return {line_id: Returned(qty, refund, cogs) for line_id, qty, refund, cogs in rows}


def list_returns(session: Session, sale_id: UUID) -> list[SaleReturn]:
    get_sale(session, sale_id)
    stmt = select(SaleReturn).where(SaleReturn.sale_id == sale_id).order_by(SaleReturn.ts)
    return list(session.scalars(stmt))


def post_return(
    session: Session, actor: Actor, business: Business, sale_id: UUID, data: ReturnCreate
) -> SaleReturn:
    """Reverse part or all of a sale: stock comes back at the cost it left with, cash goes out."""
    require_owner(actor, "process returns")
    sale = get_sale(session, sale_id)
    if session.get(SaleReturn, data.id) is not None:
        raise Conflict("return already exists")

    sale_lines = {line.id: line for line in sale.lines}
    requested = [r.sale_line_id for r in data.lines]
    if unknown := set(requested) - sale_lines.keys():
        raise NotFound(f"lines not on this sale: {sorted(map(str, unknown))}")
    if len(requested) != len(set(requested)):
        raise RuleViolation("each sale line can appear once per return")

    already = returned_by_line(session, list(sale_lines))
    products = _lock_products(session, {sale_lines[r.sale_line_id].product_id for r in data.lines})
    on_hand = qty_on_hand(session, list(products))
    starting_wac = {pid: p.wac for pid, p in products.items()}

    sale_return = SaleReturn(
        id=data.id,
        business_id=actor.business_id,
        sale_id=sale.id,
        reason=data.reason,
        refund_method=data.refund_method,
        refund_reference=data.refund_reference,
        refund_total=0,
        cogs_reversed=0,
        user_id=actor.user_id,
    )
    session.add(sale_return)
    session.flush()

    for r in data.lines:
        line = sale_lines[r.sale_line_id]
        done = already.get(line.id, Returned())
        if r.qty > line.qty - done.qty:
            raise RuleViolation(f"can return at most {line.qty - done.qty} of line {line.id}")
        refund = rules.prorate(line.line_total, r.qty, line.qty, done.qty, done.refund)
        cogs = rules.prorate(line.cogs, r.qty, line.qty, done.qty, done.cogs)
        session.add(
            ReturnLine(
                business_id=actor.business_id,
                return_id=sale_return.id,
                sale_line_id=line.id,
                qty=r.qty,
                refund=refund,
                cogs_reversed=cogs,
            )
        )
        sale_return.refund_total += refund
        sale_return.cogs_reversed += cogs

        # Goods come back at the WAC they left with, blended into the current WAC.
        product = products[line.product_id]
        product.wac = inventory.new_wac(on_hand[product.id], product.wac, r.qty, line.wac_snapshot)
        on_hand[product.id] += r.qty
        session.add(
            StockMovement(
                business_id=actor.business_id,
                product_id=product.id,
                type=inventory.MovementType.RETURN,
                qty=r.qty,
                unit_cost=line.wac_snapshot,
                wac_snapshot=product.wac,
                ref_type="sale_return",
                ref_id=sale_return.id,
                reason=data.reason,
                user_id=actor.user_id,
            )
        )

    for pid, product in products.items():
        if product.wac != starting_wac[pid]:
            audit.record(session, actor, "product", pid, "wac", starting_wac[pid], product.wac)
            propose_reprice(session, business, product, starting_wac[pid])

    if data.refund_method is PaymentMethod.CREDIT:
        # A credit customer's return lowers what they owe instead of paying cash out.
        credit.credit_note(
            session, actor, sale, sale_return.id, sale_return.refund_total, data.reason
        )
    else:
        account = cash.account_for(session, data.refund_method)
        cash.post(
            session,
            actor,
            account,
            cash.CashEntryType.REFUND,
            -sale_return.refund_total,
            "sale_return",
            sale_return.id,
        )

    session.flush()
    returned = returned_by_line(session, list(sale_lines))
    fully = all(returned.get(lid, Returned()).qty == line.qty for lid, line in sale_lines.items())
    sale.status = "returned" if fully else "partially_returned"
    session.refresh(sale_return)
    events.publish(
        session,
        events.SaleReturned(actor.business_id, sale.id, sale_return.id, sale_return.refund_total),
    )
    return sale_return
