"""Contract tests for the declarative provider layer (ADR 0002).

The CashCtrl spec is exercised end to end against the offline fake transport, which
proves the spec's param + response mappings without a network. Also covered:
capability negotiation, the grammar-cage rejections, tenant resolution, pagination,
composite-op guard, and the author-time path-finder.

Any new provider spec is "done" when it passes the same shape of tests.
"""

from __future__ import annotations

import pytest

from app.providers.errors import (
    ArgValidationError,
    ExecutionError,
    UnknownOpError,
    UnknownProviderError,
    UnsupportedOperationError,
)
from app.providers.executor import ProviderExecutor
from app.providers.fake import FakeCashCtrlTransport
from app.providers.pathfinder import propose_bindings
from app.providers.registry import ProviderRegistry
from app.providers.spec import SPECS_DIR, ProviderSpec, load_all
from app.providers.vocabulary import CANONICAL_OPS, validate_args


def _cashctrl_executor() -> ProviderExecutor:
    spec = ProviderRegistry().get("cashctrl")
    return ProviderExecutor(spec, FakeCashCtrlTransport())


async def _run(op: str, raw: dict):
    ex = _cashctrl_executor()
    vargs = validate_args(op, raw)
    return await ex.execute(op, vargs.model_dump())


# ── spec loading & invariants ─────────────────────────────────────────────


def test_specs_load_and_name_matches_filename():
    specs = load_all(SPECS_DIR)
    assert "cashctrl" in specs
    assert specs["cashctrl"].name == "cashctrl"


def test_every_spec_binds_only_canonical_ops():
    for name, spec in load_all(SPECS_DIR).items():
        unknown = spec.capabilities - set(CANONICAL_OPS)
        assert not unknown, f"{name} binds non-canonical ops: {unknown}"


def test_cashctrl_capabilities():
    caps = ProviderRegistry().get("cashctrl").capabilities
    assert caps == {"contact.lookup", "journal.list", "journal.get", "journal.create"}


# ── executor: CashCtrl spec vs fake transport (param + response mapping) ────


async def test_contact_lookup_by_name_remaps_fields():
    r = await _run("contact.lookup", {"name": "Anna"})
    assert r.count == 1
    assert r.data["id"] == 4827
    assert r.data["kind"] == "parent"  # canonical 'kind' <- wire 'type'
    assert "type" not in r.data  # wire field name did not leak through


async def test_contact_lookup_by_id():
    r = await _run("contact.lookup", {"id": 9201})
    assert r.data["name"].startswith("Elektrizitätswerk")


async def test_contact_lookup_miss_is_none():
    r = await _run("contact.lookup", {"name": "Nonexistent Person"})
    assert r.data is None
    assert r.count == 0


async def test_journal_list_scoped_by_contact_and_date():
    r = await _run(
        "journal.list",
        {"contact_name": "Anna Müller", "date_from": "2026-05-01", "date_to": "2026-05-31"},
    )
    assert [e["id"] for e in r.data] == ["JE-2026-0421", "JE-2026-0445"]
    e = r.data[0]
    # canonical snake_case fields, remapped from CashCtrl camelCase wire shape
    assert e["date"] == "2026-05-04"
    assert e["contact_id"] == 4827
    assert e["debit_account"] == 1100
    assert e["currency"] == "CHF"


async def test_journal_list_date_only_excludes_other_months():
    r = await _run("journal.list", {"date_from": "2026-05-01", "date_to": "2026-05-31"})
    ids = [e["id"] for e in r.data]
    assert ids == ["JE-2026-0421", "JE-2026-0431", "JE-2026-0445", "JE-2026-0480"]
    assert "JE-2026-0512" not in ids  # June entry correctly excluded


async def test_journal_list_unknown_contact_is_empty():
    r = await _run("journal.list", {"contact_name": "Nobody At All"})
    assert r.data == []
    assert r.count == 0


async def test_journal_get_and_miss():
    r = await _run("journal.get", {"id": "JE-2026-0445"})
    assert r.count == 1
    assert r.data["title"].startswith("Lehrmittel")
    miss = await _run("journal.get", {"id": "JE-DOES-NOT-EXIST"})
    assert miss.data is None


async def test_journal_create_maps_body_and_response():
    r = await _run(
        "journal.create",
        {
            "date": "2026-06-10",
            "amount": "99.00",
            "debit_account": 1100,
            "credit_account": 3000,
            "title": "Test",
        },
    )
    assert r.data["id"] == "JE-NEW-0001"  # canonical 'id' <- wire 'reference'
    assert r.data["debit_account"] == 1100  # canonical <- wire 'debitId'
    assert r.data["date"] == "2026-06-10"


# ── grammar cage ───────────────────────────────────────────────────────────


def test_unknown_op_rejected():
    with pytest.raises(UnknownOpError):
        validate_args("cashctrl.journal_list", {})  # old vendor name is gone
    with pytest.raises(UnknownOpError):
        validate_args("totally.bogus", {})


def test_arg_cage_rejections():
    with pytest.raises(ArgValidationError):
        validate_args("journal.get", {})  # missing required id
    with pytest.raises(ArgValidationError):
        validate_args("contact.lookup", {})  # needs id or name
    with pytest.raises(ArgValidationError):
        validate_args("journal.list", {"date_from": "01.05.2026"})  # not ISO
    with pytest.raises(ArgValidationError):
        validate_args("journal.list", {"bogus_field": 1})  # extra key forbidden


# ── capability negotiation ─────────────────────────────────────────────────


def _spec(name: str, operations: dict) -> ProviderSpec:
    return ProviderSpec.model_validate(
        {
            "name": name,
            "version": "1",
            "base_url_setting": "cashctrl_api_base",
            "operations": operations,
        }
    )


async def test_unsupported_op_is_rejected_not_executed():
    mini = _spec(
        "mini",
        {
            "contact.lookup": {
                "http": {
                    "method": "GET",
                    "path": "/person/read.json",
                    "query": {"id": {"arg": "id"}, "name": {"arg": "name"}},
                    "response": {"item_path": "data"},
                }
            },
        },
    )
    ex = ProviderExecutor(mini, FakeCashCtrlTransport())
    assert mini.supports("contact.lookup")
    assert not mini.supports("journal.list")
    with pytest.raises(UnsupportedOperationError):
        await ex.execute("journal.list", {"date_from": "2026-05-01"})


# ── composite steps (name→id resolve, then act) ────────────────────────────


async def test_journal_list_by_contact_id_uses_fallback_arg():
    """No contact_name ⇒ the resolve step is skipped and the directly-supplied
    contact_id flows into associateId via fallback_arg."""
    r = await _run("journal.list", {"contact_id": 4827})
    assert [e["id"] for e in r.data] == ["JE-2026-0421", "JE-2026-0445", "JE-2026-0512"]


async def test_steps_short_circuit_never_widens_scope():
    """A fired resolve step that misses must yield EMPTY — under no circumstances
    an unscoped query (the silently-unscoped bug class)."""
    r = await _run("journal.list", {"contact_name": "Ghost Person", "date_from": "2026-05-01"})
    assert r.data == []
    assert r.count == 0


async def test_unconsumed_arg_refused_not_dropped():
    """A provider binding that cannot honor a provided filter must refuse, not
    silently drop the filter and run the query wider than asked."""
    nofilter = _spec(
        "nofilter",
        {
            "journal.list": {
                "http": {
                    "method": "GET",
                    "path": "/journal/list.json",
                    "query": {"dateFrom": {"arg": "date_from"}, "dateTo": {"arg": "date_to"}},
                    "response": {"list_path": "data"},
                }
            },
        },
    )
    ex = ProviderExecutor(nofilter, FakeCashCtrlTransport())
    with pytest.raises(ExecutionError, match="contact_name"):
        await ex.execute("journal.list", {"contact_name": "Anna", "date_from": None})


# ── failure honesty: envelope, truncation, cursors, secrets ────────────────


class _EnvelopeFailTransport:
    async def send(self, req):
        return {"success": False, "message": "permission denied"}


async def test_http200_error_envelope_fails_loud():
    spec = _spec(
        "env",
        {
            "journal.get": {
                "http": {
                    "method": "GET",
                    "path": "/journal/read.json",
                    "query": {"id": {"arg": "id", "required": True}},
                    "response": {
                        "success_path": "success",
                        "error_message_path": "message",
                        "item_path": "data",
                    },
                }
            },
        },
    )
    ex = ProviderExecutor(spec, _EnvelopeFailTransport())
    with pytest.raises(ExecutionError, match="permission denied"):
        await ex.execute("journal.get", {"id": "JE-1"})


class _EndlessPagesTransport:
    """Always-advancing cursor — the list never ends."""

    def __init__(self) -> None:
        self.n = 0

    async def send(self, req):
        self.n += 1
        return {"items": [{"id": f"row-{self.n}"}], "next": f"c{self.n}"}


async def test_truncated_pagination_refused(monkeypatch):
    monkeypatch.setattr("app.providers.executor._MAX_PAGES", 3)
    spec = _spec(
        "endless",
        {
            "journal.list": {
                "http": {
                    "method": "GET",
                    "path": "/x",
                    "response": {
                        "list_path": "items",
                        "next_cursor_path": "next",
                        "cursor_param": "cursor",
                    },
                }
            },
        },
    )
    ex = ProviderExecutor(spec, _EndlessPagesTransport())
    with pytest.raises(ExecutionError, match="truncated"):
        await ex.execute("journal.list", {})


class _StuckCursorTransport:
    async def send(self, req):
        return {"items": [{"id": "dup"}], "next": "same-cursor"}


async def test_non_advancing_cursor_refused():
    spec = _spec(
        "stuck",
        {
            "journal.list": {
                "http": {
                    "method": "GET",
                    "path": "/x",
                    "response": {
                        "list_path": "items",
                        "next_cursor_path": "next",
                        "cursor_param": "cursor",
                    },
                }
            },
        },
    )
    ex = ProviderExecutor(spec, _StuckCursorTransport())
    with pytest.raises(ExecutionError, match="did not advance"):
        await ex.execute("journal.list", {})


def test_cursor_fields_must_be_paired():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="cursor_param"):
        _spec(
            "badcursor",
            {
                "journal.list": {
                    "http": {
                        "method": "GET",
                        "path": "/x",
                        "response": {"list_path": "items", "next_cursor_path": "next"},
                    }
                },
            },
        )


async def test_unset_secret_fails_closed(monkeypatch):
    """No credential ⇒ refuse to send, never an unauthenticated request."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "cashctrl_api_key", "")
    ex = _cashctrl_executor()
    with pytest.raises(ExecutionError, match="not configured"):
        await ex.execute("contact.lookup", {"id": 4827})


class _HeaderCaptureTransport:
    def __init__(self) -> None:
        self.headers: dict = {}

    async def send(self, req):
        self.headers = dict(req.headers)
        return {"success": True, "data": None}


async def test_per_tenant_credential_override_wins():
    spec = ProviderRegistry().get("cashctrl")
    transport = _HeaderCaptureTransport()
    ex = ProviderExecutor(
        spec, transport, credential_overrides={"cashctrl_api_key": "tenant-a-key"}
    )
    await ex.execute("contact.lookup", {"id": 4827})
    assert transport.headers["Authorization"] == "Bearer tenant-a-key"


# ── registry / tenant resolution ────────────────────────────────────────────


def test_unknown_provider_raises():
    with pytest.raises(UnknownProviderError):
        ProviderRegistry().get("bexio")


def test_tenant_resolution_default_and_binding(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "default_accounting_provider", "cashctrl")
    monkeypatch.setattr(settings, "accounting_provider_bindings", {"tenant-x": "bexio"})
    reg = ProviderRegistry()
    assert reg.provider_for_tenant("tenant-y") == "cashctrl"  # falls back to default
    assert reg.provider_for_tenant("tenant-x") == "bexio"  # explicit binding


# ── pagination (executor loop, provider-agnostic) ───────────────────────────


class _PageTransport:
    """Two-page cursor stub — asserts the executor follows next_cursor_path."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def send(self, req):
        self.calls.append(dict(req.params))
        if req.params.get("cursor") is None:
            return {"items": [{"id": "A"}], "next": "c1"}
        return {"items": [{"id": "B"}], "next": None}


async def test_executor_follows_cursor_pagination():
    spec = _spec(
        "pg",
        {
            "journal.list": {
                "http": {
                    "method": "GET",
                    "path": "/x",
                    "response": {
                        "list_path": "items",
                        "next_cursor_path": "next",
                        "cursor_param": "cursor",
                    },
                }
            },
        },
    )
    transport = _PageTransport()
    ex = ProviderExecutor(spec, transport)
    r = await ex.execute("journal.list", {})
    assert [i["id"] for i in r.data] == ["A", "B"]
    assert len(transport.calls) == 2  # exactly two pages fetched


# ── author-time path-finder ─────────────────────────────────────────────────


def test_pathfinder_proposes_plausible_endpoints():
    openapi = {
        "paths": {
            "/journal/list.json": {
                "get": {"operationId": "listJournal", "summary": "List journal entries"}
            },
            "/person/read.json": {
                "get": {"operationId": "readPerson", "summary": "Read a person / contact"}
            },
            "/journal/create.json": {
                "post": {"operationId": "createJournal", "summary": "Create a journal entry"}
            },
            "/weather": {"get": {"summary": "unrelated"}},
        }
    }
    props = propose_bindings(openapi)
    assert props["journal.list"][0].path == "/journal/list.json"
    assert props["journal.list"][0].method == "GET"
    assert props["contact.lookup"][0].path == "/person/read.json"
    assert props["journal.create"][0].method == "POST"
