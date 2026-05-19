"""Deterministic in-memory CashCtrl backend for POCs and tests.

Same query, same response, every time.  No I/O.  No network.  Mirrors the
shape of the real `app.cashctrl.client.CashCtrlClient` so the POC and tests
can swap the real client out without touching call sites.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

# ── fixtures ────────────────────────────────────────────────────────────

CONTACTS: dict[int, dict[str, Any]] = {
    4827: {
        "id": 4827,
        "name": "Anna Müller",
        "iban": "CH3608380000123456789",
        "kind": "parent",
    },
    4828: {
        "id": 4828,
        "name": "Markus Frei",
        "iban": "CH8909000000789012345",
        "kind": "parent",
    },
    9201: {
        "id": 9201,
        "name": "Elektrizitätswerk der Stadt Zürich",
        "iban": "CH0900700110000123456",
        "kind": "vendor",
    },
}

JOURNAL: list[dict[str, Any]] = [
    {
        "id": "JE-2026-0421",
        "date": "2026-05-04",
        "contact_id": 4827,
        "title": "Tuition Mai 2026 — Anna Müller",
        "amount": "1450.00",
        "currency": "CHF",
        "debit_account": 1100,
        "credit_account": 3000,
    },
    {
        "id": "JE-2026-0431",
        "date": "2026-05-08",
        "contact_id": 4828,
        "title": "Tuition Mai 2026 — Markus Frei",
        "amount": "1450.00",
        "currency": "CHF",
        "debit_account": 1100,
        "credit_account": 3000,
    },
    {
        "id": "JE-2026-0445",
        "date": "2026-05-18",
        "contact_id": 4827,
        "title": "Lehrmittel Mai 2026 — Anna Müller",
        "amount": "120.00",
        "currency": "CHF",
        "debit_account": 4500,
        "credit_account": 1100,
    },
    {
        "id": "JE-2026-0480",
        "date": "2026-05-28",
        "contact_id": 9201,
        "title": "Stromrechnung Mai 2026",
        "amount": "742.10",
        "currency": "CHF",
        "debit_account": 6500,
        "credit_account": 2000,
    },
    {
        "id": "JE-2026-0512",
        "date": "2026-06-03",
        "contact_id": 4827,
        "title": "Tuition Juni 2026 — Anna Müller",
        "amount": "1450.00",
        "currency": "CHF",
        "debit_account": 1100,
        "credit_account": 3000,
    },
]


# ── deterministic stub client ───────────────────────────────────────────


class FakeCashCtrl:
    """In-memory CashCtrl stub.  All methods are deterministic and async."""

    async def contact_lookup(
        self, *, name: str | None = None, id: int | None = None
    ) -> dict | None:
        for c in CONTACTS.values():
            if id is not None and c["id"] == id:
                return dict(c)
            if name is not None and name.strip().lower() in c["name"].lower():
                return dict(c)
        return None

    async def journal_list(
        self,
        *,
        contact_id: int | None = None,
        contact_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        if contact_name and contact_id is None:
            c = await self.contact_lookup(name=contact_name)
            if c is not None:
                contact_id = c["id"]
            else:
                return []  # unknown contact → empty result, deterministic

        out: list[dict] = []
        for je in JOURNAL:
            if contact_id is not None and je["contact_id"] != contact_id:
                continue
            if date_from and je["date"] < date_from:
                continue
            if date_to and je["date"] > date_to:
                continue
            out.append(dict(je))
        return sorted(out, key=lambda x: (x["date"], x["id"]))

    async def journal_get(self, *, id: str) -> dict | None:
        for je in JOURNAL:
            if je["id"] == id:
                return dict(je)
        return None

    async def total(self, entries: list[dict]) -> Decimal:
        """Sum the `amount` field across a list of journal entries.  Pure."""
        return sum((Decimal(e["amount"]) for e in entries), Decimal("0"))
