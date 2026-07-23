"""FakeCashCtrlTransport — an offline emulator of the CashCtrl HTTP API.

This is a *transport*, not a client: it receives the exact
:class:`~app.providers.transport.ProviderRequest` the executor built from
``specs/cashctrl.yaml`` and returns CashCtrl-*shaped* JSON. That means the whole
chain is exercised under test —

    canonical args → (spec) query params → server-side filter (here)
                   → CashCtrl wire JSON → (spec) response map → canonical result

— proving the spec's param + response mappings are correct, deterministically and
without a network. The wire shape mirrors CashCtrl's ``{"success":true,"data":…}``
envelope with camelCase fields, so the response map does real remapping work.

Fixtures are reused from ``app.cashctrl.fake`` (single source of truth). The exact
CashCtrl field names below are modeled for the reference adapter and must be
verified against the live CashCtrl API before production use (see cashctrl.yaml).
"""

from __future__ import annotations

from typing import Any

from app.cashctrl.fake import CONTACTS, JOURNAL
from app.providers.transport import ProviderRequest


def _contact_wire(c: dict[str, Any]) -> dict[str, Any]:
    """Canonical fixture → CashCtrl person wire shape."""
    return {"id": c["id"], "name": c["name"], "iban": c["iban"], "type": c["kind"]}


def _entry_wire(e: dict[str, Any]) -> dict[str, Any]:
    """Canonical fixture → CashCtrl journal wire shape (camelCase, renamed)."""
    return {
        "reference": e["id"],
        "dateAdded": e["date"],
        "associateId": e["contact_id"],
        "title": e["title"],
        "amount": e["amount"],
        "currencyCode": e["currency"],
        "debitId": e["debit_account"],
        "creditId": e["credit_account"],
    }


def _ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


def _resolve_contact(*, id: Any = None, name: Any = None) -> dict[str, Any] | None:
    for c in CONTACTS.values():
        if id is not None and c["id"] == int(id):
            return c
        if name and str(name).strip().lower() in c["name"].lower():
            return c
    return None


class FakeCashCtrlTransport:
    """Deterministic CashCtrl API emulator. Same request → same response."""

    async def send(self, req: ProviderRequest) -> Any:
        path = req.path.split("?")[0].rstrip("/")
        params = req.params or {}

        # --- person/read: lookup by id (preferred) or name substring ---
        if path.endswith("/person/read.json") or path.endswith("/person/read"):
            c = _resolve_contact(id=params.get("id"), name=params.get("name"))
            return _ok(_contact_wire(c) if c else None)

        # --- journal/list: server-side filter by associate id + date range ---
        if path.endswith("/journal/list.json") or path.endswith("/journal/list"):
            contact_id = params.get("associateId")
            date_from = params.get("dateFrom")
            date_to = params.get("dateTo")
            rows: list[dict[str, Any]] = []
            for e in JOURNAL:
                if contact_id is not None and e["contact_id"] != int(contact_id):
                    continue
                if date_from and e["date"] < date_from:
                    continue
                if date_to and e["date"] > date_to:
                    continue
                rows.append(_entry_wire(e))
            rows.sort(key=lambda r: (r["dateAdded"], r["reference"]))
            return _ok(rows)

        # --- journal/read: single entry by reference ---
        if path.endswith("/journal/read.json") or path.endswith("/journal/read"):
            ref = params.get("id")
            for e in JOURNAL:
                if e["id"] == ref:
                    return _ok(_entry_wire(e))
            return _ok(None)

        # --- journal/create: echo a deterministic created entry ---
        if path.endswith("/journal/create.json") or path.endswith("/journal/create"):
            body = req.json or {}
            created = dict(body)
            created.setdefault("reference", "JE-NEW-0001")
            return _ok(created)

        raise AssertionError(f"FakeCashCtrlTransport: unmapped path {req.path!r}")
