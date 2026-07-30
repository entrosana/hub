"""SQLAlchemy 2.x async engine + session factory + Base."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import settings


class Base(DeclarativeBase):
    """All ORM models inherit from this."""


def _build_engine():
    """Create the engine.

    SQLite (used in tests via aiosqlite) requires StaticPool — it cannot
    accept the connection-pool kwargs that Postgres uses.  Production hits
    the Postgres branch; CI / pytest hit the SQLite branch.
    """
    echo = settings.environment == "development"
    if settings.database_url.startswith("sqlite"):
        return create_async_engine(
            settings.database_url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
            echo=echo,
        )
    return create_async_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        pool_pre_ping=True,
        echo=echo,
    )


engine = _build_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session per request."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
