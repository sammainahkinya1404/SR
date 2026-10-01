from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.api.deps import Ctx
from app.domain import receipts
from app.domain.sales import PaymentMethod
from app.models import Customer, Product, Sale, SaleReturn, User
from app.schemas.sales import (
    PaymentOut,
    ReceiptOut,
    ReturnCreate,
    ReturnLineOut,
    ReturnOut,
    SaleCreate,
    SaleLineOut,
    SaleOut,
)
from app.services import sales
from app.services.sales import Returned

router = APIRouter(prefix="/sales", tags=["sales"])


def _sale_out(ctx: Ctx, sale: Sale) -> SaleOut:
    returned = sales.returned_by_line(ctx.session, [line.id for line in sale.lines])
    return SaleOut(
        id=sale.id,
        receipt_no=receipts.receipt_number(sale.receipt_no),
        subtotal=sale.subtotal,
        discount_total=sale.discount_total,
        total=sale.total,
        cogs=sale.cogs,
        gross_profit=sale.gross_profit,
        change_given=sale.change_given,
        status=sale.status,
        device_id=sale.device_id,
        customer_id=sale.customer_id,
        user_id=sale.user_id,
        ts=sale.ts,
        lines=[
            SaleLineOut(
                id=line.id,
                product_id=line.product_id,
                qty=line.qty,
                unit_price=line.unit_price,
                discount=line.discount,
                line_total=line.line_total,
                wac_snapshot=line.wac_snapshot,
                cogs=line.cogs,
                gross_profit=line.gross_profit,
                floor_override=line.floor_override,
                returned_qty=returned.get(line.id, Returned()).qty,
            )
            for line in sale.lines
        ],
        payments=[
            PaymentOut(method=PaymentMethod(p.method), amount=p.amount, mpesa_code=p.mpesa_code)
            for p in sale.payments
        ],
        refunded_total=sum(r.refund for r in returned.values()),
    )


def _return_out(sale_return: SaleReturn) -> ReturnOut:
    return ReturnOut(
        id=sale_return.id,
        sale_id=sale_return.sale_id,
        reason=sale_return.reason,
        refund_method=PaymentMethod(sale_return.refund_method),
        refund_reference=sale_return.refund_reference,
        refund_total=sale_return.refund_total,
        cogs_reversed=sale_return.cogs_reversed,
        ts=sale_return.ts,
        lines=[
            ReturnLineOut(
                sale_line_id=line.sale_line_id,
                qty=line.qty,
                refund=line.refund,
                cogs_reversed=line.cogs_reversed,
            )
            for line in sale_return.lines
        ],
    )


@router.post("", status_code=201, response_model=SaleOut)
def post_sale(data: SaleCreate, ctx: Ctx, response: Response):
    sale, created = sales.post_sale(ctx.session, ctx.actor, ctx.business, data)
    if not created:
        response.status_code = 200  # replay of a sale already posted
    return _sale_out(ctx, sale)


@router.get("", response_model=list[SaleOut])
def list_sales(
    ctx: Ctx,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(default=50, ge=1, le=500),
):
    return [_sale_out(ctx, s) for s in sales.list_sales(ctx.session, since, until, limit)]


@router.get("/{sale_id}", response_model=SaleOut)
def get_sale(sale_id: UUID, ctx: Ctx):
    return _sale_out(ctx, sales.get_sale(ctx.session, sale_id))


@router.get("/{sale_id}/receipt", response_model=ReceiptOut)
def get_receipt(sale_id: UUID, ctx: Ctx):
    sale = sales.get_sale(ctx.session, sale_id)
    out = _sale_out(ctx, sale)
    names = dict(
        ctx.session.execute(
            select(Product.id, Product.name).where(
                Product.id.in_([line.product_id for line in sale.lines])
            )
        ).all()
    )
    cashier = ctx.session.get(User, sale.user_id)
    customer = ctx.session.get(Customer, sale.customer_id) if sale.customer_id else None
    text = receipts.render(
        business_name=ctx.business.name,
        receipt_no=sale.receipt_no,
        ts=sale.ts,
        cashier=cashier.name if cashier else "",
        lines=[
            receipts.ReceiptLine(
                name=names[line.product_id],
                qty=line.qty,
                unit_price=line.unit_price,
                discount=line.discount,
                line_total=line.line_total,
            )
            for line in sale.lines
        ],
        total=sale.total,
        payments=[receipts.ReceiptPayment(p.method, p.amount, p.mpesa_code) for p in sale.payments],
        change=sale.change_given,
        refunded=out.refunded_total,
        customer=customer.name if customer else None,
    )
    return ReceiptOut(receipt_no=out.receipt_no, text=text)


@router.post("/{sale_id}/returns", status_code=201, response_model=ReturnOut)
def post_return(sale_id: UUID, data: ReturnCreate, ctx: Ctx):
    return _return_out(sales.post_return(ctx.session, ctx.actor, ctx.business, sale_id, data))


@router.get("/{sale_id}/returns", response_model=list[ReturnOut])
def list_returns(sale_id: UUID, ctx: Ctx):
    return [_return_out(r) for r in sales.list_returns(ctx.session, sale_id)]
