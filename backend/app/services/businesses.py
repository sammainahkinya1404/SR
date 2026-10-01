from sqlalchemy.orm import Session

from app.models import Business, User
from app.schemas.businesses import BusinessCreate, SettingsOut, SettingsUpdate, UserCreate
from app.services import audit, cash, expenses
from app.services.actor import Actor, Role, require_owner
from app.services.errors import Conflict, NotFound


def create_business(session: Session, data: BusinessCreate) -> Business:
    """Opening a business also creates its owner. The session must already be scoped to data.id."""
    if session.get(Business, data.id) is not None:
        raise Conflict("business already exists")
    business = Business(id=data.id, name=data.name)
    session.add(business)
    session.flush()
    session.add(
        User(
            id=data.owner_id,
            business_id=business.id,
            name=data.owner_name,
            phone=data.owner_phone,
            role=Role.OWNER,
        )
    )
    cash.create_default_accounts(session, business.id)
    expenses.create_default_categories(session, business.id)
    session.flush()
    return business


def get_business(session: Session, actor: Actor) -> Business:
    business = session.get(Business, actor.business_id)
    if business is None:
        raise NotFound("business not found")
    return business


def create_user(session: Session, actor: Actor, data: UserCreate) -> User:
    require_owner(actor, "add users")
    if session.get(User, data.id) is not None:
        raise Conflict("user already exists")
    user = User(
        id=data.id, business_id=actor.business_id, name=data.name, phone=data.phone, role=data.role
    )
    session.add(user)
    session.flush()
    return user


def settings_out(business: Business) -> SettingsOut:
    return SettingsOut(
        name=business.name,
        price_rounding_cents=business.price_rounding,
        price_floor_pct=business.price_floor_pct,
        reprice_threshold_pct=business.reprice_threshold_pct,
        trading_days_per_month=business.trading_days_per_month,
        default_allocation_method=business.default_allocation_method,
        default_target_margin=business.default_target_margin,
        alert_low_cash_days=business.alert_low_cash_days,
        alert_credit_risk_pct=business.alert_credit_risk_pct,
        alert_slow_moving_days=business.alert_slow_moving_days,
        alert_max_days_of_stock=business.alert_max_days_of_stock,
    )


def update_settings(
    session: Session, actor: Actor, business: Business, data: SettingsUpdate
) -> Business:
    require_owner(actor, "change business settings")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if "price_rounding_cents" in changes:
        changes["price_rounding"] = changes.pop("price_rounding_cents")
    for field, value in changes.items():
        old = getattr(business, field)
        if old != value:
            audit.record(session, actor, "business", business.id, field, old, value)
            setattr(business, field, value)
    return business
