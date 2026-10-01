from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import Ctx
from app.config import get_settings
from app.db import system_session, tenant_session
from app.models import Business, User
from app.schemas.businesses import (
    BusinessCreate,
    BusinessOut,
    MeOut,
    SetupOut,
    SetupUser,
    UserCreate,
    UserOut,
)
from app.services import businesses
from app.services.actor import require_owner
from app.services.errors import Conflict

router = APIRouter(tags=["businesses"])


@router.post("/businesses", status_code=201, response_model=BusinessOut)
def create_business(data: BusinessCreate) -> BusinessOut:
    """Unauthenticated one-time setup: opens the shop and its owner account."""
    if get_settings().single_shop:
        with system_session() as session:
            existing = session.scalar(select(Business.name))
        if existing is not None:
            raise Conflict(f"this system is already set up for {existing}")
    with tenant_session(data.id) as session:
        business = businesses.create_business(session, data)
        return BusinessOut(id=business.id, name=business.name, owner_id=data.owner_id)


@router.get("/setup", response_model=SetupOut)
def setup_status() -> SetupOut:
    """Unauthenticated: whether the shop is set up, and who can sign in.

    DEV AUTH ONLY: listing users to pick from stands in for owner OTP / cashier PIN sign-in."""
    with system_session() as session:
        business = session.scalars(select(Business).order_by(Business.created_at)).first()
        if business is None:
            return SetupOut(configured=False, business_id=None, business_name=None, users=[])
        users = session.scalars(
            select(User)
            .where(User.business_id == business.id)
            .order_by(User.role.desc(), User.name)
        ).all()
        return SetupOut(
            configured=True,
            business_id=business.id,
            business_name=business.name,
            users=[SetupUser(id=u.id, name=u.name, role=u.role) for u in users],
        )


@router.post("/users", status_code=201, response_model=UserOut)
def create_user(data: UserCreate, ctx: Ctx):
    return businesses.create_user(ctx.session, ctx.actor, data)


@router.get("/me", response_model=MeOut)
def me(ctx: Ctx):
    """Who the current headers identify: lets a client confirm a sign-in and show the business."""
    user = ctx.session.get(User, ctx.actor.user_id)
    return MeOut(user=user, business_id=ctx.business.id, business_name=ctx.business.name)


@router.get("/users", response_model=list[UserOut])
def list_users(ctx: Ctx):
    require_owner(ctx.actor, "list users")
    return ctx.session.scalars(select(User).order_by(User.role.desc(), User.name)).all()
