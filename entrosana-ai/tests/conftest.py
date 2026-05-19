"""Pytest fixtures shared across the suite.

Each test gets an in-memory SQLite database with the full schema created
from `Base.metadata`. The `db` fixture yields an `AsyncSession`; the
`client` fixture yields an httpx test client wired against the same
session via FastAPI dependency override.
"""
import os

# Force the test environment BEFORE any app module imports settings.
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-do-not-use-in-prod")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DLM_AUDIT_HMAC_KEY", "test-audit-hmac-key")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Importing app.main triggers SQLAlchemy mapper configuration, which is
# what we need for Base.metadata to see every table.
from app.main import app  # noqa: E402,F401
from app.core.database import Base, get_session  # noqa: E402


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def client(db):
    async def _override_session():
        yield db

    app.dependency_overrides[get_session] = _override_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
