"""Tests for database setup and disabled tracing behavior."""

from fastapi import FastAPI

from app.core import database, tracing


def test_build_engine_uses_sqlite_static_pool(monkeypatch):
    calls = []

    def fake_create(url, **kwargs):
        calls.append((url, kwargs))
        return "sqlite-engine"

    monkeypatch.setattr(database, "create_async_engine", fake_create)
    monkeypatch.setattr(database.settings, "database_url", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setattr(database.settings, "environment", "development")

    assert database._build_engine() == "sqlite-engine"
    assert calls[0][1]["poolclass"] is database.StaticPool
    assert calls[0][1]["connect_args"] == {"check_same_thread": False}
    assert calls[0][1]["echo"] is True


def test_build_engine_uses_postgres_pool_options(monkeypatch):
    calls = []

    def fake_create(url, **kwargs):
        calls.append((url, kwargs))
        return "postgres-engine"

    monkeypatch.setattr(database, "create_async_engine", fake_create)
    monkeypatch.setattr(database.settings, "database_url", "postgresql+asyncpg://db")
    monkeypatch.setattr(database.settings, "database_pool_size", 13)
    monkeypatch.setattr(database.settings, "environment", "test")

    assert database._build_engine() == "postgres-engine"
    assert calls[0] == (
        "postgresql+asyncpg://db",
        {"pool_size": 13, "pool_pre_ping": True, "echo": False},
    )


def test_setup_tracing_is_noop_without_exporter(monkeypatch):
    monkeypatch.setattr(tracing.settings, "otel_exporter_otlp_endpoint", None)

    app = FastAPI()
    tracing.setup_tracing(app)

    assert len(app.routes) == 4
