from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from uuid import UUID

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import ORMExecuteState, Session, sessionmaker, with_loader_criteria

from app.config import get_settings
from app.models import Business
from app.models.base import TenantMixin


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record) -> None:
        # Let SQLAlchemy emit BEGIN itself (below) instead of pysqlite's lazy BEGIN.
        dbapi_conn.isolation_level = None
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn) -> None:
        # SQLite ignores SELECT ... FOR UPDATE. Taking the write lock when the transaction starts
        # serializes postings, so read-then-write steps (qty on hand -> new WAC) cannot race.
        conn.exec_driver_sql("BEGIN IMMEDIATE")


@lru_cache
def get_engine() -> Engine:
    engine = create_engine(get_settings().database_url)
    if engine.dialect.name == "sqlite":
        _configure_sqlite(engine)
    return engine


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def reset_engine() -> None:
    """Drop the cached settings and engine so the next session uses the current DATABASE_URL."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    for cached in (get_settings, get_engine, _session_factory):
        cached.cache_clear()


@contextmanager
def tenant_session(business_id: UUID) -> Iterator[Session]:
    """One transaction scoped to a business: the only way the app should open a session.

    Tenant isolation lives here while we are on SQLite (the spec's Postgres RLS will back it up
    later): every ORM query is filtered to this business, and flushes refuse rows for another."""
    with _session_factory()() as session, session.begin():
        session.info["business_id"] = business_id
        yield session


@contextmanager
def system_session() -> Iterator[Session]:
    """Unscoped session for cross-business jobs (e.g. listing businesses). Reads see every
    business; any write is refused by the flush guard because no business is set."""
    with _session_factory()() as session, session.begin():
        yield session


@event.listens_for(Session, "do_orm_execute")
def _scope_to_business(state: ORMExecuteState) -> None:
    business_id = state.session.info.get("business_id")
    if business_id is None or not (state.is_select or state.is_update or state.is_delete):
        return
    state.statement = state.statement.options(
        with_loader_criteria(
            TenantMixin, lambda cls: cls.business_id == business_id, include_aliases=True
        ),
        with_loader_criteria(Business, Business.id == business_id),
    )


@event.listens_for(Session, "before_flush")
def _guard_writes(session: Session, _ctx, _instances) -> None:
    if session.deleted:
        raise RuntimeError("hard deletes are not allowed: post a reversal instead")
    business_id = session.info.get("business_id")
    for obj in session.new | session.dirty:
        owner = obj.id if isinstance(obj, Business) else getattr(obj, "business_id", None)
        if owner != business_id:
            raise RuntimeError(f"{type(obj).__name__} does not belong to the current business")
