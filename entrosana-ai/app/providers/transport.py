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
    """Real HTTP transport. Creates a short-lived client per call.

    (A pooled client is a later optimization; per-call keeps lifecycle trivially
    correct and there is no shared mutable state to leak between tenants.)
    """

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    async def send(self, req: ProviderRequest) -> Any:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.request(
                    req.method,
                    req.url,
                    headers=req.headers or None,
                    params=req.params or None,
                    json=req.json,
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.HTTPError as e:
            raise ExecutionError(f"transport error calling {req.method} {req.url}: {e}") from e
        except ValueError as e:  # non-JSON body
            raise ExecutionError(f"non-JSON response from {req.url}: {e}") from e
