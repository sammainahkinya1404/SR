"""Profit figures (spec Part A §9). Phase 5 adds periods, break-even and the dashboard."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Expense, OwnerEntry, Sale, SaleReturn


@dataclass(frozen=True)
class ProfitToDate:
    gross_profit: int  # sales GP less the GP given back by returns
    operating_expenses: int  # includes automatic losses; reversals net out
    net_profit: int
    drawings: int  # cash and in-kind; never part of expenses


def profit_to_date(session: Session) -> ProfitToDate:
    session.flush()
    sales_gp = session.scalar(select(func.coalesce(func.sum(Sale.gross_profit), 0)))
    returned_gp = session.scalar(
        select(func.coalesce(func.sum(SaleReturn.refund_total - SaleReturn.cogs_reversed), 0))
    )
    opex = session.scalar(select(func.coalesce(func.sum(Expense.amount), 0)))
    drawings = session.scalar(
        select(func.coalesce(func.sum(OwnerEntry.amount), 0)).where(OwnerEntry.type == "drawing")
    )
    gross_profit = sales_gp - returned_gp
    return ProfitToDate(gross_profit, opex, gross_profit - opex, drawings)
