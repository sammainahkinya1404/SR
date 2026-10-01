from alembic import context
from sqlalchemy import create_engine

from app.config import get_settings
from app.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    # Tests override the URL through the Alembic config; otherwise use the settings.
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(), target_metadata=target_metadata, literal_binds=True, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        # Batch mode lets autogenerate express ALTERs that SQLite cannot do in place.
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
