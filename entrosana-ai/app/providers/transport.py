"""Transport — the seam between the deterministic executor and the wire.

The executor builds a fully-resolved :class:`ProviderRequest` (method, url, path,
headers, params, json) from the spec + validated args, then hands it to a
``Transport``. Production uses :class:`HttpxTransport`; tests use
``app.providers.fake.FakeCashCtrlTransport`` (fixture-backed, no network) so a spec
is exercised end to end without touching a real API.

Keeping the executor transport-agnostic is what makes the whole layer testable and
offline-capable: same request-building code path, swappable wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import httpx

from app.providers.errors import ExecutionError

# Shared, lazily-created async HTTP client.  Reusing one client keeps the
# underlying connection pool warm and avoids per-call TCP/TLS overhead.
_HTTP_CLIENT: httpx.AsyncClient | None = None


def _http_limits() -> httpx.Limits:
    """Connection pool limits for the shared client.

    Defaults match httpx's defaults but are explicit so they can be tuned.
    """
    return httpx.Limits(max_keepalive_connections=20, max_connections=100)


def get_http_client() -> httpx.AsyncClient:
    """Return the shared ``httpx.AsyncClient``.

    The first call creates it; subsequent calls reuse the same pool.  The
    caller MUST NOT close this client directly — use :func:`close_http_client`
    during application shutdown.
    """
    global _HTTP_CLIENT
    if _HTTP_CLIENT is None:
        _HTTP_CLIENT = httpx.AsyncClient(
            limits=_http_limits(),
            # HTTP/2 requires the optional ``h2`` package; enable only when it
            # is added to the dependency set.  Keep-alive + pooling still apply.
            http2=False,
        )
    return _HTTP_CLIENT


async def close_http_client() -> None:
    """Close the shared HTTP client.  Call this once on application shutdown."""
    global _HTTP_CLIENT
    if _HTTP_CLIENT is not None:
        await _HTTP_CLIENT.aclose()
        _HTTP_CLIENT = None


@dataclass(frozen=True, slots=True)
class ProviderRequest:
    """A fully-resolved provider call. Pure data — no I/O."""

    method: str
    url: str  # absolute URL (base + path), used by real transport
    path: str  # templated path only, used by the fake to route
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)  # querystring
    json: dict[str, Any] | None = None  # request body


@runtime_checkable
class Transport(Protocol):
    async def send(self, req: ProviderRequest) -> Any:
        """Execute the request and return the parsed JSON (dict or list)."""
        ...


class HttpxTransport:
    """Real HTTP transport backed by a shared ``httpx.AsyncClient`` pool."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._client = client or get_http_client()
        self._timeout = timeout

    async def send(self, req: ProviderRequest) -> Any:
        try:
            resp = await self._client.request(
                req.method,
                req.url,
                headers=req.headers or None,
                params=req.params or None,
                json=req.json,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise ExecutionError(f"transport error calling {req.method} {req.url}: {e}") from e
        except ValueError as e:  # non-JSON body
            raise ExecutionError(f"non-JSON response from {req.url}: {e}") from e
