"""Alembic env.  Async-compatible setup against the app's models."""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import settings
from app.core.database import Base

# Import models so Base.metadata sees them
from app.audit import models as _  # noqa: F401
from app.identity import models as _i  # noqa: F401
from app.accounting import models as _a  # noqa: F401
from app.admin import models as _ad  # noqa: F401
from app.scheduling import models as _s  # noqa: F401
from app.contracts import models as _c  # noqa: F401
from app.expenses import models as _e  # noqa: F401
from app.taxes import models as _t  # noqa: F401
from app.signup import models as _si  # noqa: F401
from app.addresses import models as _add  # noqa: F401
from app.billing import models as _b  # noqa: F401
from app.documents import models as _d  # noqa: F401
from app.providers import models as _p  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("+asyncpg", ""))
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = settings.database_url
    connectable = async_engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online():
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    raise RuntimeError("offline migrations not supported")
run_migrations_online()
