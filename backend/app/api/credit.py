"""Credit customers, repayments, write-offs, ageing and reminders. Cashiers can look customers up
and take repayments at the till; everything else is owner-only (enforced in the services or
here for read-only reports)."""

import datetime as dt
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import Ctx
from app.api.exports import Format, ksh, table
from app.domain import credit as rules
from app.domain.clock import business_today
from app.domain.receipts import receipt_number
from app.models import Customer, Sale
from app.schemas.credit import (
    AgeingOut,
    AgeingRow,
    CreditEntryOut,
    CustomerCreate,
    CustomerOut,
    CustomerUpdate,
    InvoiceOut,
    RepaymentCreate,
    SmsOut,
    StatementOut,
    WriteOffCreate,
)
from app.services import credit, reminders
from app.services.actor import require_owner

router = APIRouter(tags=["credit"])


def _customer_out(ctx: Ctx, customer: Customer) -> CustomerOut:
    summary = credit.summarize(ctx.session, customer)
    return CustomerOut(
        id=customer.id,
        name=customer.name,
        phone=customer.phone,
        id_number=customer.id_number,
        credit_limit_cents=customer.credit_limit,
        terms_days=customer.terms_days,
        active=customer.active,
        balance_cents=summary.balance,
        overdue_cents=summary.overdue,
        available_credit_cents=summary.available,
    )


@router.get("/customers", response_model=list[CustomerOut])
def list_customers(ctx: Ctx, q: str | None = None):
    return [_customer_out(ctx, c) for c in credit.list_customers(ctx.session, q)]


@router.post("/customers", status_code=201, response_model=CustomerOut)
def create_customer(data: CustomerCreate, ctx: Ctx):
    return _customer_out(ctx, credit.create_customer(ctx.session, ctx.actor, data))


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: UUID, ctx: Ctx):
    return _customer_out(ctx, credit.get_customer(ctx.session, customer_id))


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: UUID, data: CustomerUpdate, ctx: Ctx):
    return _customer_out(ctx, credit.update_customer(ctx.session, ctx.actor, customer_id, data))


@router.get("/customers/{customer_id}/statement", response_model=StatementOut)
def customer_statement(customer_id: UUID, ctx: Ctx):
    require_owner(ctx.actor, "view customer statements")
    customer = credit.get_customer(ctx.session, customer_id)
    today = business_today()
    invoices = credit.open_invoices(ctx.session, customer.id)
    sale_ids = [i.charge.sale_id for i in invoices if i.charge.sale_id]
    receipts = dict(
        ctx.session.execute(select(Sale.id, Sale.receipt_no).where(Sale.id.in_(sale_ids))).all()
    )
    return StatementOut(
        customer=_customer_out(ctx, customer),
        open_invoices=[
            InvoiceOut(
                charge_id=i.charge.id,
                sale_id=i.charge.sale_id,
                receipt_no=receipt_number(receipts[i.charge.sale_id])
                if i.charge.sale_id in receipts
                else None,
                date=i.charge.ts,
                due_date=i.charge.due_date,
                amount=i.charge.amount,
                outstanding=i.outstanding,
                days_overdue=max(0, rules.days_overdue(i.charge.due_date, today)),
                bucket=rules.bucket(i.charge.due_date, today),
            )
            for i in invoices
        ],
        ageing=rules.ageing([i.open() for i in invoices], today),
        entries=[
            CreditEntryOut.model_validate(e) for e in credit.statement(ctx.session, customer.id)
        ],
    )


@router.post("/customers/{customer_id}/repayments", status_code=201, response_model=CreditEntryOut)
def record_repayment(customer_id: UUID, data: RepaymentCreate, ctx: Ctx):
    return credit.record_repayment(ctx.session, ctx.actor, customer_id, data)


@router.post("/customers/{customer_id}/write-offs", status_code=201, response_model=CreditEntryOut)
def write_off(customer_id: UUID, data: WriteOffCreate, ctx: Ctx):
    return credit.write_off(ctx.session, ctx.actor, customer_id, data)


@router.get("/credit/ageing", response_model=AgeingOut)
def ageing_report(ctx: Ctx, as_of: dt.date | None = None, format: Format = Format.JSON):
    require_owner(ctx.actor, "view the ageing report")
    as_of = as_of or business_today()
    rows, totals = credit.ageing_report(ctx.session, as_of)
    if format is not Format.JSON:
        buckets = list(rules.AgeingBucket)
        return table(
            format,
            f"credit-ageing-{as_of}",
            ["customer", "phone", "balance_ksh", *(f"{b}_ksh" for b in buckets)],
            [
                [c.name, c.phone, ksh(total), *(ksh(amounts[b]) for b in buckets)]
                for c, total, amounts in rows
            ],
        )
    return AgeingOut(
        as_of=as_of,
        rows=[
            AgeingRow(
                customer_id=c.id, name=c.name, phone=c.phone, balance_cents=total, buckets=buckets
            )
            for c, total, buckets in rows
        ],
        totals=totals,
        total_cents=sum(totals.values()),
    )


@router.post("/credit/reminders/run", response_model=list[SmsOut])
def queue_reminders(ctx: Ctx):
    """Queue today's reminders. The daily job (`python -m app.jobs credit-reminders`) does the
    same for every business."""
    require_owner(ctx.actor, "queue credit reminders")
    return reminders.queue_credit_reminders(ctx.session, ctx.business)


@router.get("/sms-outbox", response_model=list[SmsOut])
def sms_outbox(ctx: Ctx, status: str | None = "pending"):
    require_owner(ctx.actor, "view queued SMS")
    return reminders.list_outbox(ctx.session, status)
