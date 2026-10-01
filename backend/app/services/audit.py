from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.services.actor import Actor


def record(
    session: Session,
    actor: Actor,
    entity: str,
    entity_id: UUID,
    field: str,
    old: object,
    new: object,
) -> None:
    """Audit a change to price, cost, stock or cash (spec Part A §11)."""
    session.add(
        AuditLog(
            business_id=actor.business_id,
            entity=entity,
            entity_id=entity_id,
            field=field,
            old=None if old is None else str(old),
            new=None if new is None else str(new),
            user_id=actor.user_id,
        )
    )
