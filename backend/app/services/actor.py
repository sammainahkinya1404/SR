from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from app.services.errors import Forbidden


class Role(StrEnum):
    OWNER = "owner"
    CASHIER = "cashier"


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    business_id: UUID
    role: Role


def require_owner(actor: Actor, action: str) -> None:
    if actor.role is not Role.OWNER:
        raise Forbidden(f"only the owner can {action}")
