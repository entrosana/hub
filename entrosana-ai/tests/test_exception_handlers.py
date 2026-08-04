"""Tests for the centralized exception handlers."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import HTTPException
from httpx import ASGITransport, AsyncClient

from app.core.exceptions import add_exception_handlers
from app.providers.errors import ExecutionError


async def test_provider_error_returns_problem_response() -> None:
    app = FastAPI()
    add_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise ExecutionError("upstream failed")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/boom")

    assert r.status_code == 502
    body = r.json()
    assert body["detail"] == "upstream failed"
    assert body["status"] == 502
    assert body["type"] == "ExecutionError"


async def test_http_exception_returns_problem_response() -> None:
    app = FastAPI()
    add_exception_handlers(app)

    @app.get("/nope")
    async def nope() -> None:
        raise HTTPException(401, "go away")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.get("/nope")

    assert r.status_code == 401
    body = r.json()
    assert body["detail"] == "go away"
    assert body["status"] == 401
    assert body["type"] == "HTTPException"
