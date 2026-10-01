from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.db import tenant_session
from app.models import Business, User
from app.services.actor import Actor, Role


@dataclass
class Context:
    session: Session
    actor: Actor
    business: Business


# Declared as security schemes rather than parameters, so /docs gets an "Authorize" button and
# generated clients don't have to pass them on every call.
business_header = APIKeyHeader(name="X-Business-Id", description="Dev auth stub: business id")
user_header = APIKeyHeader(name="X-User-Id", description="Dev auth stub: user id")


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(401, "unknown business or user") from None


def _context(
    x_business_id: Annotated[str, Security(business_header)],
    x_user_id: Annotated[str, Security(user_header)],
) -> Iterator[Context]:
    """DEV AUTH ONLY: trusts identity headers. Phase work on auth replaces this with owner
    phone+OTP / cashier device PIN and short-lived JWTs (spec Part B §9); keep the Context shape.

    The transaction commits when the route returns and rolls back on any exception."""
    business_id, user_id = _uuid(x_business_id), _uuid(x_user_id)
    with tenant_session(business_id) as session:
        # The session is scoped to the business, so a user id from another business is not found.
        user = session.get(User, user_id)
        business = session.get(Business, business_id)
        if user is None or business is None:
            raise HTTPException(401, "unknown business or user")
        yield Context(session, Actor(user.id, user.business_id, Role(user.role)), business)


# scope="function" ends the dependency (and commits) before the response is sent, so a failed
# commit surfaces as an error instead of a 2xx for data that was never saved.
Ctx = Annotated[Context, Depends(_context, scope="function")]
