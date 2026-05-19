"""End-to-end example: a Swiss school using the DLM for bookkeeping.

Run directly to see propose · audit · sign · verify in action:

    python -m app.dlm.base.example_school

Also importable: `app.dlm.base.example_school.dlm` is a ready DLM,
`build_agent(key_hex)` returns a wired Agent.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path

from .core import (
    DLM,
    Agent,
    AuditTrail,
    Features,
    Grammar,
    HmacSigner,
    Lexicon,
    SignedAction,
    Template,
    Tenant,
    Term,
    Tier,
    Verifier,
    audit_chain,
)

# ── Lexicon: closed vocabulary ──────────────────────────────────────────

LEXICON = Lexicon.of(
    "2026-05",
    vendors=[
        Term(
            "V_EWZ",
            "Elektrizitätswerk der Stadt Zürich",
            aliases=("EWZ", "ewz"),
            attrs=(
                ("iban", "CH0900700110000123456"),
                ("debit", "6500"),
                ("credit", "2000"),
                ("vat", "0.081"),
                ("cost_center", "HEIZUNG"),
            ),
        ),
        Term(
            "V_MIGROS",
            "Migros Gastronomie AG",
            aliases=("Migros", "Migros Gastro"),
            attrs=(
                ("debit", "4400"),
                ("credit", "2000"),
                ("vat", "0.026"),
                ("cost_center", "MENSA"),
            ),
        ),
    ],
    accounts=[
        Term("1100", "Forderungen aus L+L"),
        Term("2000", "Verbindlichkeiten aus L+L"),
        Term("4400", "Lebensmittel Mensa"),
        Term("5800", "Verbrauchsmaterial"),
        Term("6500", "Strom / Wasser / Heizung"),
    ],
    doc_types=[
        Term("RECHNUNG", "Rechnung", attrs=(("sign", "+1"),)),
        Term("GUTSCHRIFT", "Gutschrift", attrs=(("sign", "-1"),)),
    ],
)


# ── Confidence signals ──────────────────────────────────────────────────


def iban_known(template, bindings, doc, lexicon) -> Decimal:
    iban = doc.get("vendor_iban")
    if not iban:
        return Decimal("-0.40")
    for v in lexicon.category("vendors"):
        if v.attr("iban") == iban:
            return Decimal("0.10")
    return Decimal("-0.30")


def vat_in_swiss_set(template, bindings, doc, lexicon) -> Decimal:
    return (
        Decimal("0.05")
        if bindings.get("vat_rate") in {"0", "0.026", "0.038", "0.081"}
        else Decimal("0")
    )


# ── Grammar: composition rules ──────────────────────────────────────────

GRAMMAR = Grammar(
    version="2026-05",
    templates=(
        Template(
            template_id="QRBILL_STANDARD",
            requires=("vendor_iban", "amount", "currency"),
            matchers=(
                ("currency", r"CHF"),
                ("amount", r"(?P<amt>\d+\.\d{2})"),
            ),
            binds=(("doc_type", "RECHNUNG"),),
            base_confidence=Decimal("0.80"),
        ),
        Template(
            template_id="ALIAS_LINE",
            requires=("vendor_name", "amount"),
            matchers=(("amount", r"(?P<amt>\d+\.\d{2})"),),
            binds=(("doc_type", "RECHNUNG"),),
            base_confidence=Decimal("0.50"),
        ),
    ),
)


# ── Module-level DLM (so verify_replay can import it) ───────────────────

dlm = DLM(LEXICON, GRAMMAR, signals=(iban_known, vat_in_swiss_set))


def build_dlm() -> DLM:
    return dlm


def build_agent(key_hex: str, key_id: str = "2026-q2") -> Agent:
    signer = HmacSigner(key=bytes.fromhex(key_hex), key_id=key_id)
    tenant = Tenant(
        id="school-zh",
        threshold_auto=Decimal("0.92"),
        threshold_second=Decimal("0.65"),
    )
    return Agent(tenant, dlm, signer)


# ── A simple append-only audit store ────────────────────────────────────


class JsonlStore:
    def __init__(self, path: Path):
        self.path = path

    def append(self, entry: dict) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps(entry, default=str, sort_keys=True) + "\n")


# ── Demo flow ───────────────────────────────────────────────────────────


def demo() -> None:
    key_hex = os.environ.get("DLM_KEY") or ("ab" * 32)
    agent = build_agent(key_hex)
    audit = AuditTrail(JsonlStore(Path("audit.jsonl")))

    feat = Features.of(
        doc_id="inv-2026-001",
        content_hash="sha256:" + "0" * 64,
        fields={
            "vendor_iban": "CH0900700110000123456",
            "amount": "412.50",
            "currency": "CHF",
        },
    )

    decision = agent.propose(feat)
    print(f"tier:       {decision.tier_required.value}")
    print(f"confidence: {decision.confidence}")
    print(f"value:      {dict(decision.value)}")
    print(f"run_id:     {decision.run_id}")
    print(f"dlm_fp:     {decision.dlm_fp[:16]}…")

    approver = None if decision.tier_required is Tier.AUTO else "director@school.ch"
    receipt = audit.record(decision, approver=approver)
    action = SignedAction.from_receipt(
        receipt,
        kind="booking",
        payload={
            "date_added": "2026-05-19",
            "title": "EWZ Stromrechnung Mai 2026",
            "debit_account_id": "6500",
            "credit_account_id": "2000",
            "amount": "412.50",
        },
    )
    print(f"\naction kind: {action.kind}")
    print("action ready for Sink.commit(action)")

    verifier = Verifier({"2026-q2": bytes.fromhex(key_hex)})
    results = audit_chain(decision, features=feat, dlm=agent.dlm, verifier=verifier)
    print("\naudit chain:")
    for check, (ok, reason) in results.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {check}: {reason}")


if __name__ == "__main__":
    demo()
