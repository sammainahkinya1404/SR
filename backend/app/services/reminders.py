"""SMS reminders for credit invoices (spec Part A §6). They are queued in `sms_outbox`; sending
through an SMS gateway (Africa's Talking) is an integration for later."""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import credit as rules
from app.domain.clock import business_today
from app.domain.receipts import receipt_number
from app.models import Business, Customer, Sale, SmsOutbox
from app.services import credit


def queue_credit_reminders(
    session: Session, business: Business, today: dt.date | None = None
) -> list[SmsOutbox]:
    """Queue a reminder for every open invoice due today or overdue. Each invoice gets at most one
    'due' and one 'overdue' message, however often this runs."""
    today = today or business_today()
    invoices = credit.open_invoices(session)
    if not invoices:
        return []
    already = {
        (kind, ref) for kind, ref in session.execute(select(SmsOutbox.kind, SmsOutbox.ref_id))
    }
    customer_ids = {i.charge.customer_id for i in invoices}
    customers = {
        c.id: c for c in session.scalars(select(Customer).where(Customer.id.in_(customer_ids)))
    }
    balances = credit.balances(session, list(customer_ids))
    sale_ids = [i.charge.sale_id for i in invoices if i.charge.sale_id]
    receipts = dict(
        session.execute(select(Sale.id, Sale.receipt_no).where(Sale.id.in_(sale_ids))).all()
    )

    queued = []
    for invoice in invoices:
        kind = rules.reminder_kind(invoice.charge.due_date, today)
        customer = customers[invoice.charge.customer_id]
        if kind is None or not customer.phone or (kind, invoice.charge.id) in already:
            continue
        receipt = receipts.get(invoice.charge.sale_id)
        message = SmsOutbox(
            business_id=business.id,
            phone=customer.phone,
            message=rules.reminder_message(
                kind,
                business_name=business.name,
                customer_name=customer.name,
                receipt_no=receipt_number(receipt) if receipt else "-",
                outstanding=invoice.outstanding,
                due_date=invoice.charge.due_date,
                balance=balances.get(customer.id, 0),
            ),
            kind=kind,
            ref_type="credit_charge",
            ref_id=invoice.charge.id,
            status="pending",
        )
        session.add(message)
        queued.append(message)
    session.flush()
    return queued


def list_outbox(session: Session, status: str | None) -> list[SmsOutbox]:
    stmt = select(SmsOutbox).order_by(SmsOutbox.created_at.desc())
    if status is not None:
        stmt = stmt.where(SmsOutbox.status == status)
    return list(session.scalars(stmt))
