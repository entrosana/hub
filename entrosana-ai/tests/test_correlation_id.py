"""Correlation-ID middleware tests."""

import re

import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.middleware import CorrelationIdMiddleware


async def test_missing_request_id_is_generated(client):
    response = await client.get("/health")

    request_id = response.headers["X-Request-ID"]
    assert response.status_code == 200
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)


async def test_request_id_is_echoed(client):
    response = await client.get("/health", headers={"X-Request-ID": "my-fixed-id"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "my-fixed-id"


async def test_request_context_is_bound_and_cleared():
    test_app = FastAPI()
    test_app.add_middleware(CorrelationIdMiddleware)

    @test_app.get("/context")
    async def context():
        return structlog.contextvars.get_contextvars()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.get("/context", headers={"X-Request-ID": "context-id"})

    assert response.json()["request_id"] == "context-id"
    assert structlog.contextvars.get_contextvars() == {}
