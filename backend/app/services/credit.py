"""Customer credit (spec Part A §6): customers, invoices from credit sales, repayments applied to
the oldest invoices first, write-offs, credit notes from returns, and ageing."""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain import credit as rules
from app.domain.clock import business_today
from app.domain.credit import CreditEntryType, OpenInvoice
from app.domain.sales import PaymentMethod
from app.models import CreditAllocation, CreditLedger, Customer, Sale
from app.schemas.credit import CustomerCreate, CustomerUpdate, RepaymentCreate, WriteOffCreate
from app.services import audit, cash, expenses, mpesa
from app.services.actor import Actor, require_owner
from app.services.errors import Conflict, NotFound, RuleViolation


@dataclass(frozen=True)
class Invoice:
    charge: CreditLedger
    outstanding: int

    def open(self) -> OpenInvoice:
        return OpenInvoice(self.charge.id, self.charge.due_date, self.outstanding)


@dataclass(frozen=True)
class CustomerSummary:
    customer: Customer
    balance: int
    overdue: int

    @property
    def available(self) -> int:
        return max(0, self.customer.credit_limit - self.balance)


# Customers --------------------------------------------------------------------------------------


def create_customer(session: Session, actor: Actor, data: CustomerCreate) -> Customer:
    require_owner(actor, "add credit customers")
    if session.get(Customer, data.id) is not None:
        raise Conflict("customer already exists")
    customer = Customer(
        id=data.id,
        business_id=actor.business_id,
        name=data.name,
        phone=data.phone,
        id_number=data.id_number,
        credit_limit=data.credit_limit_cents,
        terms_days=data.terms_days,
        active=True,
    )
    session.add(customer)
    session.flush()
    return customer


def update_customer(
    session: Session, actor: Actor, customer_id: UUID, data: CustomerUpdate
) -> Customer:
    require_owner(actor, "change credit customers")
    customer = get_customer(session, customer_id)
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "credit_limit_cents" in changes:
        changes["credit_limit"] = changes.pop("credit_limit_cents")
    for field, value in changes.items():
        old = getattr(customer, field)
        if old != value:
            if field in ("credit_limit", "terms_days"):
                audit.record(session, actor, "customer", customer.id, field, old, value)
            setattr(customer, field, value)
    return customer


def get_customer(session: Session, customer_id: UUID) -> Customer:
    customer = session.get(Customer, customer_id)
    if customer is None:
        raise NotFound("customer not found")
    return customer


def list_customers(session: Session, search: str | None) -> list[Customer]:
    stmt = select(Customer).order_by(Customer.name)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(Customer.name.ilike(like) | Customer.phone.ilike(like))
    return list(session.scalars(stmt))


# Balances and invoices --------------------------------------------------------------------------


def balances(session: Session, customer_ids: list[UUID] | None = None) -> dict[UUID, int]:
    session.flush()
    stmt = select(CreditLedger.customer_id, func.sum(CreditLedger.amount)).group_by(
        CreditLedger.customer_id
    )
    if customer_ids is not None:
        stmt = stmt.where(CreditLedger.customer_id.in_(customer_ids))
    return dict(session.execute(stmt).all())


def open_invoices(session: Session, customer_id: UUID | None = None) -> list[Invoice]:
    """Charges with money still owed, oldest first (all customers when customer_id is None)."""
    session.flush()
    paid = (
        select(CreditAllocation.charge_id, func.sum(CreditAllocation.amount).label("paid"))
        .group_by(CreditAllocation.charge_id)
        .subquery()
    )
    stmt = (
        select(CreditLedger, func.coalesce(paid.c.paid, 0))
        .outerjoin(paid, paid.c.charge_id == CreditLedger.id)
        .where(CreditLedger.type == CreditEntryType.CHARGE)
        .order_by(CreditLedger.ts, CreditLedger.id)
    )
    if customer_id is not None:
        stmt = stmt.where(CreditLedger.customer_id == customer_id)
    invoices = [Invoice(charge, charge.amount - paid) for charge, paid in session.execute(stmt)]
    return [i for i in invoices if i.outstanding > 0]


def summarize(
    session: Session, customer: Customer, today: dt.date | None = None
) -> CustomerSummary:
    today = today or business_today()
    balance = balances(session, [customer.id]).get(customer.id, 0)
    overdue = sum(
        i.outstanding for i in open_invoices(session, customer.id) if i.charge.due_date < today
    )
    return CustomerSummary(customer, balance, overdue)


def statement(session: Session, customer_id: UUID) -> list[CreditLedger]:
    get_customer(session, customer_id)
    stmt = (
        select(CreditLedger)
        .where(CreditLedger.customer_id == customer_id)
        .order_by(CreditLedger.ts, CreditLedger.id)
    )
    return list(session.scalars(stmt))


# Postings ---------------------------------------------------------------------------------------


def credit_sale_blocks(
    session: Session, customer: Customer, amount: int, today: dt.date | None = None
) -> list[str]:
    summary = summarize(session, customer, today)
    return rules.credit_blocks(summary.balance, customer.credit_limit, amount, summary.overdue)


def charge_sale(
    session: Session, actor: Actor, customer: Customer, sale: Sale, amount: int
) -> None:
    """A credit sale raises an invoice due after the customer's payment terms."""
    session.add(
        CreditLedger(
            business_id=actor.business_id,
            customer_id=customer.id,
            type=CreditEntryType.CHARGE,
            amount=amount,
            due_date=business_today() + timedelta(days=customer.terms_days),
            sale_id=sale.id,
            ref_type="sale",
            ref_id=sale.id,
            user_id=actor.user_id,
        )
    )


def _reduce(
    session: Session,
    actor: Actor,
    customer: Customer,
    entry_type: CreditEntryType,
    amount: int,
    *,
    prefer_sale_id: UUID | None = None,
    entry_id: UUID | None = None,
    **fields,
) -> CreditLedger:
    """Post an entry that lowers what the customer owes, allocated oldest invoice first."""
    invoices = open_invoices(session, customer.id)
    prefer = next((i.charge.id for i in invoices if i.charge.sale_id == prefer_sale_id), None)
    try:
        parts = rules.allocate([i.open() for i in invoices], amount, prefer)
    except ValueError as e:
        raise RuleViolation(f"{customer.name}: {e}") from e
    entry = CreditLedger(
        business_id=actor.business_id,
        customer_id=customer.id,
        type=entry_type,
        amount=-amount,
        user_id=actor.user_id,
        **fields,
    )
    if entry_id is not None:
        entry.id = entry_id
    session.add(entry)
    session.flush()
    for charge_id, part in parts:
        session.add(
            CreditAllocation(
                business_id=actor.business_id, entry_id=entry.id, charge_id=charge_id, amount=part
            )
        )
    session.flush()
    return entry


def record_repayment(
    session: Session, actor: Actor, customer_id: UUID, data: RepaymentCreate
) -> CreditLedger:
    """Cashiers can take repayments at the till; partial payments are fine."""
    customer = get_customer(session, customer_id)
    if session.get(CreditLedger, data.id) is not None:
        raise Conflict("repayment already exists")
    if data.method is PaymentMethod.CREDIT:
        raise RuleViolation("repayments come in as cash or M-Pesa")
    code = None
    if data.method is PaymentMethod.MPESA:
        code = mpesa.normalize(data.mpesa_code)
        mpesa.ensure_unused(session, [code])
    elif data.mpesa_code:
        raise RuleViolation("only M-Pesa repayments take a transaction code")
    account = cash.account_for(session, data.method)
    entry = _reduce(
        session,
        actor,
        customer,
        CreditEntryType.REPAYMENT,
        data.amount_cents,
        entry_id=data.id,
        account_id=account.id,
        mpesa_code=code,
        note=data.note,
    )
    cash.post(
        session, actor, account, cash.CashEntryType.REPAYMENT, data.amount_cents, "credit", entry.id
    )
    return entry


def write_off(
    session: Session, actor: Actor, customer_id: UUID, data: WriteOffCreate
) -> CreditLedger:
    """Owner only. Unrecoverable debt becomes a 'Bad debt' expense (no money moves)."""
    require_owner(actor, "write off customer debt")
    customer = get_customer(session, customer_id)
    if session.get(CreditLedger, data.id) is not None:
        raise Conflict("write-off already exists")
    entry = _reduce(
        session,
        actor,
        customer,
        CreditEntryType.WRITEOFF,
        data.amount_cents,
        entry_id=data.id,
        note=data.reason,
    )
    expense = expenses.post_expense(
        session,
        actor,
        date=business_today(),
        category=expenses.category_named(session, expenses.BAD_DEBT),
        amount=data.amount_cents,
        account_id=None,
        note=f"{customer.name}: {data.reason}",
        source=expenses.ExpenseSource.BAD_DEBT,
        ref_type="credit",
        ref_id=entry.id,
    )
    audit.record(session, actor, "customer", customer.id, "write_off", None, expense.amount)
    return entry


def credit_note(
    session: Session, actor: Actor, sale: Sale, return_id: UUID, amount: int, reason: str
) -> CreditLedger:
    """Goods returned from a credit sale reduce the debt instead of paying cash out. The sale's own
    invoice is cleared first."""
    if sale.customer_id is None:
        raise RuleViolation("only sales to a credit customer can be refunded to credit")
    customer = get_customer(session, sale.customer_id)
    return _reduce(
        session,
        actor,
        customer,
        CreditEntryType.CREDIT_NOTE,
        amount,
        prefer_sale_id=sale.id,
        sale_id=sale.id,
        ref_type="sale_return",
        ref_id=return_id,
        note=reason,
    )


# Ageing -----------------------------------------------------------------------------------------


def ageing_report(
    session: Session, today: dt.date | None = None
) -> tuple[list[tuple[Customer, int, dict]], dict]:
    """Per customer and in total: outstanding invoices by days overdue (spec Part A §6)."""
    today = today or business_today()
    by_customer: dict[UUID, list[OpenInvoice]] = defaultdict(list)
    for invoice in open_invoices(session):
        by_customer[invoice.charge.customer_id].append(invoice.open())
    customers = {
        c.id: c for c in session.scalars(select(Customer).where(Customer.id.in_(by_customer)))
    }
    rows = []
    totals = dict.fromkeys(rules.AgeingBucket, 0)
    for customer_id, invoices in by_customer.items():
        buckets = rules.ageing(invoices, today)
        for key, value in buckets.items():
            totals[key] += value
        rows.append((customers[customer_id], sum(buckets.values()), buckets))
    rows.sort(key=lambda row: -row[1])
    return rows, totals
