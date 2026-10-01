"""M-Pesa transaction codes, typed in by hand until the Daraja integration verifies them."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.sales import MPESA_CODE
from app.models import CreditLedger, Payment
from app.services.errors import Conflict, RuleViolation


def normalize(code: str | None) -> str:
    code = (code or "").strip().upper()
    if not MPESA_CODE.match(code):
        raise RuleViolation("M-Pesa payments need the 10-character transaction code")
    return code


def ensure_unused(session: Session, codes: list[str]) -> None:
    """A code proves one payment, so it may appear once across sales and credit repayments."""
    if not codes:
        return
    if len(codes) != len(set(codes)):
        raise RuleViolation("the same M-Pesa code appears twice")
    used = session.scalar(
        select(Payment.id).where(Payment.mpesa_code.in_(codes))
    ) or session.scalar(select(CreditLedger.id).where(CreditLedger.mpesa_code.in_(codes)))
    if used:
        raise Conflict("that M-Pesa code has already been used")
