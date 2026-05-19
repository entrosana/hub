"""Pytest fixtures shared across the suite."""

# Env defaults — must be set BEFORE any `app.*` import so Settings() can load.
import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("DLM_AUDIT_HMAC_KEY", "test-hmac-key-for-audit-chain-testing-only")

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
