from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.config import settings
from app.database import Base

target_metadata = Base.metadata


def run_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    with create_engine(settings.DATABASE_URL).connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
