"""Typed errors for the provider layer.

Kept separate so callers (dispatcher, endpoint) can map each to an HTTP status
without importing pydantic/httpx internals.
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base for every provider-layer failure."""


class UnknownOpError(ProviderError):
    """The router proposed an op that is not in the canonical vocabulary.

    This is the grammar cage rejecting a hallucinated tool: no execution happens.
    """

    def __init__(self, op_name: str) -> None:
        self.op_name = op_name
        super().__init__(f"unknown canonical op: {op_name!r}")


class ArgValidationError(ProviderError):
    """Proposed args failed the canonical op's pydantic schema (the cage)."""

    def __init__(self, op_name: str, detail: str) -> None:
        self.op_name = op_name
        self.detail = detail
        super().__init__(f"invalid args for {op_name!r}: {detail}")


class SpecError(ProviderError):
    """A provider spec is malformed or references an unknown op."""


class UnknownProviderError(ProviderError):
    """No spec is registered under the requested provider name."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"no accounting provider registered as {provider!r}")


class UnsupportedOperationError(ProviderError):
    """The resolved provider has no binding for this canonical op.

    Capability negotiation: the op is valid, but *this* backend does not
    implement it (e.g. a file-based provider that cannot post live entries).
    """

    def __init__(self, provider: str, op_name: str) -> None:
        self.provider = provider
        self.op_name = op_name
        super().__init__(f"provider {provider!r} does not support {op_name!r}")


class ExecutionError(ProviderError):
    """The provider call itself failed (transport, HTTP status, bad response)."""
