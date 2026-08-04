"""Tests for shared HTTP client pooling."""

from __future__ import annotations

import httpx

from app.providers.transport import HttpxTransport, close_http_client, get_http_client


async def test_http_client_is_shared() -> None:
    client1 = get_http_client()
    client2 = get_http_client()
    assert client1 is client2
    assert isinstance(client1, httpx.AsyncClient)


async def test_httpx_transport_uses_shared_client() -> None:
    transport = HttpxTransport()
    assert transport._client is get_http_client()


async def test_close_http_client_resets_singleton() -> None:
    old_client = get_http_client()
    await close_http_client()
    new_client = get_http_client()
    assert new_client is not old_client
    assert isinstance(new_client, httpx.AsyncClient)
