"""Deterministic Language Model — compact base.

A DLM is a transducer over (Lexicon, Grammar). Identical input + identical
artifacts → identical output bytes, forever. Replay is a theorem, not a hope.

Plug-in surfaces: Lexicon · Grammar · ConfidenceSignal · AuditStore · Sink.
Everything else is fixed.

Requires Python 3.10+.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol

# ════════════════════════════════════════════════════════════════════════
# Determinism primitives — one source of truth for "what bytes are these?"
# ════════════════════════════════════════════════════════════════════════


def canonical(obj: Any) -> bytes:
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_default,
    ).encode("utf-8")


def _default(x: Any) -> Any:
    if isinstance(x, Decimal):
        return f"{x:f}"
    if isinstance(x, datetime):
        return x.isoformat()
    if isinstance(x, tuple):
        return list(x)
    if hasattr(x, "__dataclass_fields__"):
        return asdict(x)
    if isinstance(x, Enum):
        return x.value
    raise TypeError(f"non-canonical: {type(x).__name__}")


def fingerprint(obj: Any) -> str:
    return hashlib.sha256(canonical(obj)).hexdigest()


def _clamp(d: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), d))


# ════════════════════════════════════════════════════════════════════════
# Signing — HMAC with key-id namespacing for rotation
# ════════════════════════════════════════════════════════════════════════


class Signer(Protocol):
    def sign(self, payload: bytes) -> str: ...
    @property
    def key_id(self) -> str: ...


class HmacSigner:
    def __init__(self, key: bytes, key_id: str):
        if len(key) < 32:
            raise ValueError("HMAC key must be at least 32 bytes")
        self._key, self._key_id = key, key_id

    @property
    def key_id(self) -> str:
        return self._key_id

    def sign(self, payload: bytes) -> str:
        mac = hmac.new(self._key, payload, hashlib.sha256).hexdigest()
        return f"{self._key_id}:{mac}"


class Verifier:
    """Holds multiple keys to verify decisions signed across rotations."""

    def __init__(self, keys: Mapping[str, bytes]):
        for kid, k in keys.items():
            if len(k) < 32:
                raise ValueError(f"key {kid} too short")
        self._keys = dict(keys)

    def verify(self, payload: bytes, signature: str) -> bool:
        try:
            kid, mac = signature.split(":", 1)
        except ValueError:
            return False
        key = self._keys.get(kid)
        if key is None:
            return False
        expected = hmac.new(key, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(mac, expected)


# ════════════════════════════════════════════════════════════════════════
# Lexicon — the words the system knows
# ════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Term:
    code: str
    label: str
    aliases: tuple[str, ...] = ()
    attrs: tuple[tuple[str, str], ...] = ()

    def attr(self, k: str, default: str = "") -> str:
        for ak, av in self.attrs:
            if ak == k:
                return av
        return default


@dataclass(frozen=True, slots=True)
class Lexicon:
    version: str
    categories: tuple[tuple[str, tuple[Term, ...]], ...]

    @property
    def fp(self) -> str:
        return fingerprint({"version": self.version, "categories": self.categories})

    def category(self, name: str) -> tuple[Term, ...]:
        for n, terms in self.categories:
            if n == name:
                return terms
        return ()

    def by_alias(self, category: str) -> dict[str, Term]:
        return {
            a.lower(): t for t in self.category(category) for a in (t.code, t.label, *t.aliases)
        }

    @classmethod
    def of(cls, version: str, **categories: Iterable[Term]) -> Lexicon:
        return cls(
            version=version, categories=tuple((n, tuple(ts)) for n, ts in categories.items())
        )


# ════════════════════════════════════════════════════════════════════════
# Grammar — how words compose into facts
# ════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Template:
    template_id: str
    requires: tuple[str, ...]
    matchers: tuple[tuple[str, str], ...]
    binds: tuple[tuple[str, str], ...]
    base_confidence: Decimal


@dataclass(frozen=True, slots=True)
class Grammar:
    version: str
    templates: tuple[Template, ...]

    @property
    def fp(self) -> str:
        return fingerprint({"version": self.version, "templates": self.templates})


# ════════════════════════════════════════════════════════════════════════
# Features / Candidate / Decision
# ════════════════════════════════════════════════════════════════════════


class Provenance(str, Enum):
    """Where the input came from.  Recorded on Features and Decision, signed."""

    RECORD = "record"  # System of record (e.g. CashCtrl).  Deterministic.
    USER = "user"  # Direct entry by an authenticated actor.  Deterministic.
    PROVIDER = "provider"  # Third-party API (banks, Swissdec, etc.).  Non-deterministic.


@dataclass(frozen=True, slots=True)
class Features:
    doc_id: str
    content_hash: str
    fields: tuple[tuple[str, str], ...]
    provenance: Provenance = Provenance.RECORD
    provider: str = ""  # populated iff provenance == PROVIDER

    def get(self, k: str, default: str = "") -> str:
        for fk, fv in self.fields:
            if fk == k:
                return fv
        return default

    @classmethod
    def of(
        cls,
        *,
        doc_id: str,
        content_hash: str,
        fields: Mapping[str, str],
        provenance: Provenance = Provenance.RECORD,
        provider: str = "",
    ) -> Features:
        return cls(doc_id, content_hash, tuple(sorted(fields.items())), provenance, provider)


@dataclass(frozen=True, slots=True)
class Candidate:
    template_id: str
    bindings: tuple[tuple[str, str], ...]
    confidence: Decimal
    reasons: tuple[str, ...]

    @property
    def value(self) -> dict[str, str]:
        return dict(self.bindings)


class Tier(str, Enum):
    AUTO = "auto"
    SECOND = "second"
    OWNER = "owner"


@dataclass(frozen=True, slots=True)
class Decision:
    document_id: str
    content_hash: str
    value: tuple[tuple[str, str], ...]
    confidence: Decimal
    alternatives: tuple[Candidate, ...]
    tier_required: Tier
    run_id: str
    dlm_fp: str
    tenant_id: str
    signed_at: datetime
    signature: str
    provenance: Provenance = Provenance.RECORD
    provider: str = ""


def _signing_payload(
    *,
    document_id: str,
    content_hash: str,
    value: tuple,
    confidence: Decimal,
    dlm_fp: str,
    tenant_id: str,
    signed_at: datetime,
    provenance: Provenance,
    provider: str,
) -> bytes:
    """Canonical bytes that get signed.

    Provenance fields are appended only when non-default so older Decisions
    (provenance=RECORD, no provider) keep their original signed payload.
    """
    payload: dict[str, Any] = {
        "document_id": document_id,
        "content_hash": content_hash,
        "value": list(value),
        "confidence": confidence,
        "dlm_fp": dlm_fp,
        "tenant_id": tenant_id,
        "signed_at": signed_at,
    }
    if provenance != Provenance.RECORD or provider:
        payload["provenance"] = provenance
        payload["provider"] = provider
    return canonical(payload)


# ════════════════════════════════════════════════════════════════════════
# DLM — the transducer
# ════════════════════════════════════════════════════════════════════════

ConfidenceSignal = Callable[[Template, dict, Features, Lexicon], Decimal]


class DLM:
    def __init__(
        self,
        lexicon: Lexicon,
        grammar: Grammar,
        *,
        signals: Iterable[ConfidenceSignal] = (),
        top_k: int = 10,
    ):
        self.lexicon = lexicon
        self.grammar = grammar
        self.signals = tuple(signals)
        self.top_k = top_k
        self._compiled = {
            t.template_id: tuple((f, re.compile(p)) for f, p in t.matchers)
            for t in grammar.templates
        }

    @property
    def fp(self) -> str:
        return fingerprint(
            {
                "lexicon": self.lexicon.fp,
                "grammar": self.grammar.fp,
                "signals": tuple(s.__qualname__ for s in self.signals),
            }
        )

    def propose(self, doc: Features) -> tuple[Candidate, ...]:
        out: list[Candidate] = []
        for t in self.grammar.templates:
            c = self._apply(t, doc)
            if c is not None:
                out.append(c)
        out.sort(key=lambda c: (-c.confidence, c.template_id))
        return tuple(out[: self.top_k])

    def _apply(self, t: Template, doc: Features) -> Candidate | None:
        for req in t.requires:
            if not doc.get(req):
                return None

        bindings: dict[str, str] = {}
        for field, regex in self._compiled[t.template_id]:
            v = doc.get(field)
            m = regex.fullmatch(v)
            if m is None:
                return None
            bindings[field] = v
            bindings.update({k: g for k, g in m.groupdict().items() if g is not None})

        score = t.base_confidence
        reasons: list[str] = []
        for sig in self.signals:
            delta = sig(t, bindings, doc, self.lexicon)
            if delta != 0:
                reasons.append(f"{sig.__qualname__}:{delta:+.3f}")
            score = _clamp(score + delta)

        for out_field, expr in t.binds:
            if expr.startswith("$"):
                src = expr[1:]
                if src in bindings:
                    bindings[out_field] = bindings[src]
            else:
                bindings[out_field] = expr

        return Candidate(
            template_id=t.template_id,
            bindings=tuple(sorted(bindings.items())),
            confidence=score,
            reasons=tuple(reasons),
        )


# ════════════════════════════════════════════════════════════════════════
# Tenant + Agent
# ════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class Tenant:
    id: str
    threshold_auto: Decimal
    threshold_second: Decimal


class Agent:
    """propose · route · sign."""

    def __init__(self, tenant: Tenant, dlm: DLM, signer: Signer):
        self.tenant = tenant
        self.dlm = dlm
        self.signer = signer

    def propose(self, doc: Features) -> Decision:
        candidates = self.dlm.propose(doc)
        if candidates:
            value, conf = candidates[0].bindings, candidates[0].confidence
        else:
            value, conf = (), Decimal("0")

        tier = self._route(conf)
        signed_at = datetime.now(UTC)
        payload = _signing_payload(
            document_id=doc.doc_id,
            content_hash=doc.content_hash,
            value=value,
            confidence=conf,
            dlm_fp=self.dlm.fp,
            tenant_id=self.tenant.id,
            signed_at=signed_at,
            provenance=doc.provenance,
            provider=doc.provider,
        )
        signature = self.signer.sign(payload)
        run_id = hashlib.sha256(payload + signature.encode()).hexdigest()[:24]
        return Decision(
            document_id=doc.doc_id,
            content_hash=doc.content_hash,
            value=value,
            confidence=conf,
            alternatives=candidates,
            tier_required=tier,
            run_id=run_id,
            dlm_fp=self.dlm.fp,
            tenant_id=self.tenant.id,
            signed_at=signed_at,
            signature=signature,
            provenance=doc.provenance,
            provider=doc.provider,
        )

    def _route(self, c: Decimal) -> Tier:
        if c >= self.tenant.threshold_auto:
            return Tier.AUTO
        if c >= self.tenant.threshold_second:
            return Tier.SECOND
        return Tier.OWNER


# ════════════════════════════════════════════════════════════════════════
# Audit trail — type-enforced ordering
# ════════════════════════════════════════════════════════════════════════


class AuditStore(Protocol):
    def append(self, entry: dict[str, Any]) -> None: ...


@dataclass(frozen=True, slots=True)
class AuditReceipt:
    run_id: str
    decision: Decision
    approver: str | None
    approved_at: datetime


class AuditTrail:
    def __init__(self, store: AuditStore):
        self._store = store

    def record(self, d: Decision, *, approver: str | None) -> AuditReceipt:
        if d.tier_required is not Tier.AUTO and approver is None:
            raise ValueError(f"{d.tier_required.value} review requires approver")
        now = datetime.now(UTC)
        self._store.append(
            {
                "run_id": d.run_id,
                "document_id": d.document_id,
                "content_hash": d.content_hash,
                "value": list(d.value),
                "confidence": str(d.confidence),
                "alternatives": [
                    {
                        "template_id": c.template_id,
                        "bindings": list(c.bindings),
                        "confidence": str(c.confidence),
                        "reasons": list(c.reasons),
                    }
                    for c in d.alternatives
                ],
                "tier_required": d.tier_required.value,
                "dlm_fp": d.dlm_fp,
                "tenant_id": d.tenant_id,
                "signed_at": d.signed_at.isoformat(),
                "signature": d.signature,
                "approver": approver,
                "approved_at": now.isoformat(),
            }
        )
        return AuditReceipt(d.run_id, d, approver, now)


# ════════════════════════════════════════════════════════════════════════
# Action sink — pluggable downstream system
# ════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class SignedAction:
    kind: str
    payload: tuple[tuple[str, str], ...]
    receipt: AuditReceipt

    @classmethod
    def from_receipt(
        cls, receipt: AuditReceipt, *, kind: str, payload: Mapping[str, str]
    ) -> SignedAction:
        return cls(kind=kind, payload=tuple(sorted(payload.items())), receipt=receipt)


class Sink(Protocol):
    def commit(self, action: SignedAction) -> str: ...


# ════════════════════════════════════════════════════════════════════════
# Verification — the whole point
# ════════════════════════════════════════════════════════════════════════


def verify_signature(d: Decision, v: Verifier) -> bool:
    payload = _signing_payload(
        document_id=d.document_id,
        content_hash=d.content_hash,
        value=d.value,
        confidence=d.confidence,
        dlm_fp=d.dlm_fp,
        tenant_id=d.tenant_id,
        signed_at=d.signed_at,
        provenance=d.provenance,
        provider=d.provider,
    )
    return v.verify(payload, d.signature)


def witnessed_against_distribution(
    original: Decision,
    rerun: tuple[Candidate, ...],
    *,
    prob_floor: Decimal = Decimal("0.01"),
) -> tuple[bool, str]:
    new_value = rerun[0].bindings if rerun else ()
    if new_value == original.value:
        return True, "exact match across fingerprints"
    for alt in original.alternatives:
        if alt.bindings == new_value:
            if alt.confidence >= prob_floor:
                return True, f"in original top-k at p={alt.confidence:.3f}"
            return False, f"in top-k but below floor (p={alt.confidence:.3f})"
    return False, "outside original distribution — drift"


def replay(d: Decision, dlm: DLM, features: Features) -> tuple[bool, str]:
    """Same fp → must be bit-identical (theorem). Different fp → witness."""
    rerun = dlm.propose(features)
    if dlm.fp == d.dlm_fp:
        new_value = rerun[0].bindings if rerun else ()
        if new_value == d.value:
            return True, "exact (same fingerprint, theorem)"
        return False, "FATAL: same fingerprint, different value — corruption"
    return witnessed_against_distribution(d, rerun)


def audit_chain(
    decision: Decision,
    *,
    features: Features,
    dlm: DLM,
    verifier: Verifier,
) -> dict[str, tuple[bool, str]]:
    """Independent third-party check. Returns the whole truth in one dict."""
    sig_ok = verify_signature(decision, verifier)
    content_ok = features.content_hash == decision.content_hash
    return {
        "signature": (sig_ok, "HMAC validated" if sig_ok else "signature INVALID"),
        "content": (content_ok, "input matches recorded hash" if content_ok else "INPUT TAMPERED"),
        "replay": replay(decision, dlm, features),
    }
