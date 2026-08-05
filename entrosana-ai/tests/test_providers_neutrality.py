"""Proof that the provider kernel carries no domain knowledge.

Passing the accounting tests only shows nothing broke. Neutrality is a different
claim, so it gets its own evidence: a domain that has nothing to do with
accounting is registered, bound, and executed end-to-end through the same
vocabulary, spec loader, executor, and registry — with no kernel change.

Registrations are made through ``monkeypatch``/local objects so they never leak
into the global vocabulary other tests assert against.
"""

from __future__ import annotations

import pytest

from app.providers.errors import SpecError
from app.providers.executor import ProviderExecutor
from app.providers.registry import BindingSource, ProviderRegistry
from app.providers.spec import ProviderSpec
from app.providers.vocabulary import (
    CANONICAL_OPS,
    CanonicalArgs,
    CanonicalOp,
    OpKind,
    ResultKind,
    register_ops,
    validate_args,
)

# ── a domain with no relation to accounting ───────────────────────────────


class BookGetArgs(CanonicalArgs):
    id: str


BOOK_GET = CanonicalOp("book.get", OpKind.QUERY, ResultKind.OBJECT, BookGetArgs)

LIBRARY_SPEC = {
    "name": "libsys",
    "version": "1",
    "base_url_setting": "library_api_base",
    "auth": {"kind": "none"},
    "operations": {
        "book.get": {
            "http": {
                "method": "GET",
                "path": "/books/{id}",
                "response": {
                    "item_path": "data",
                    "fields": {"id": "bookId", "title": "name"},
                },
            }
        }
    },
}


class _OneShotTransport:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.seen: list[str] = []

    async def send(self, req):
        self.seen.append(req.path)
        return self.payload


# The base URL is supplied through the per-tenant override seam, so this test
# needs no deployment settings at all.
_BASE = {"library_api_base": "https://api.library.test"}


@pytest.fixture
def library(monkeypatch):
    """Register the foreign domain for one test only."""

    monkeypatch.setitem(CANONICAL_OPS, "book.get", BOOK_GET)
    return ProviderSpec.model_validate(LIBRARY_SPEC)


async def test_kernel_runs_a_non_accounting_domain_end_to_end(library):
    transport = _OneShotTransport({"data": {"bookId": "b-7", "name": "Der Prozess"}})
    executor = ProviderExecutor(library, transport, credential_overrides=_BASE)
    result = await executor.execute("book.get", {"id": "b-7"})

    assert result.op == "book.get"
    assert result.source == "libsys"
    assert result.data == {"id": "b-7", "title": "Der Prozess"}  # canonical <- wire
    assert result.count == 1
    assert transport.seen == ["/books/b-7"]
    # the guarantees added for accounting apply here too, because they are kernel-level
    assert len(result.data_sha256) == 64


async def test_the_arg_cage_works_for_any_domain(library):
    from app.providers.errors import ArgValidationError

    assert validate_args("book.get", {"id": "b-7"}).id == "b-7"
    with pytest.raises(ArgValidationError):
        validate_args("book.get", {"id": "b-7", "smuggled": "x"})


async def test_binding_source_needs_no_settings(library):
    """A deployment can bind tenants however it likes — settings are one option."""

    class InMemoryBinding:
        async def provider_for_tenant(self, tenant_id, session=None):
            return "libsys"

        async def credentials_for_tenant(self, tenant_id, session=None):
            return {}

    assert isinstance(InMemoryBinding(), BindingSource)
    registry = ProviderRegistry(specs={"libsys": library}, binding=InMemoryBinding())
    assert await registry.provider_for_tenant("any-tenant") == "libsys"
    assert (await registry.resolve("any-tenant")).name == "libsys"


def test_vocabulary_rejects_vendor_names_and_silent_redefinition():
    with pytest.raises(SpecError, match="dotted lowercase"):
        register_ops(CanonicalOp("CashCtrl_Journal", OpKind.QUERY, ResultKind.LIST, BookGetArgs))

    other = CanonicalOp("journal.list", OpKind.QUERY, ResultKind.LIST, BookGetArgs)
    with pytest.raises(SpecError, match="already registered"):
        register_ops(other)  # a second pack must not silently take over an op


def test_kernel_modules_declare_no_operations():
    """The vocabulary module itself must not hard-code any op.

    If this fails, someone put domain knowledge back into the kernel.
    """

    import inspect

    from app.providers import vocabulary

    source = inspect.getsource(vocabulary)
    assert "CANONICAL_OPS: dict[str, CanonicalOp] = {}" in source
    assert "journal." not in source and "contact." not in source
