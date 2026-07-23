"""Canonical, provider-neutral accounting vocabulary.

This is the *only* thing the intent router (Mock or Claude) is allowed to emit,
and the *only* contract a provider spec binds against. It is deliberately small
and stable so a small offline model can be grammar-caged onto it: the model picks
one ``name`` from ``CANONICAL_OPS`` and fills the matching ``args_model``; nothing
else is accepted.

Design rules:
  * Op names are ``<object>.<verb>`` — never a vendor name. ``cashctrl.*`` is gone.
  * Arg models set ``extra="forbid"`` so a hallucinated argument is rejected before
    any provider call (the cage). Args are canonical; the per-provider spec maps
    them to that backend's HTTP params.
  * Dates are ISO ``YYYY-MM-DD`` (normalization already converts Swiss DMY upstream).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError, model_validator

from app.providers.errors import ArgValidationError, UnknownOpError

# ISO calendar date, e.g. "2026-05-01". Validated shape only (not calendar-correct);
# the provider is the source of fact for what the date actually resolves to.
IsoDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class OpKind(str, Enum):
    QUERY = "query"  # reads; safe to execute immediately
    MUTATION = "mutation"  # writes; must go through propose → confirm


class ResultKind(str, Enum):
    OBJECT = "object"  # single object, or None if not found
    LIST = "list"  # list of objects (possibly empty)


# ── canonical arg models (the grammar cage's typed contract) ──────────────


class _Args(BaseModel):
    """Base for all arg models: reject unknown keys so an LLM cannot smuggle in
    an argument the executor never validated."""

    model_config = ConfigDict(extra="forbid")


class ContactLookupArgs(_Args):
    id: int | None = None
    name: str | None = None

    @model_validator(mode="after")
    def _need_one(self) -> ContactLookupArgs:
        if self.id is None and not (self.name and self.name.strip()):
            raise ValueError("contact.lookup requires 'id' or a non-empty 'name'")
        return self


class JournalListArgs(_Args):
    contact_id: int | None = None
    contact_name: str | None = None
    date_from: IsoDate | None = None
    date_to: IsoDate | None = None


class JournalGetArgs(_Args):
    id: str


class JournalCreateArgs(_Args):
    date: IsoDate
    amount: str  # decimal string; never a float (audit-grade money)
    debit_account: int
    credit_account: int
    title: str
    contact_id: int | None = None
    currency: str = "CHF"


# ── canonical op registry ─────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CanonicalOp:
    name: str
    kind: OpKind
    result: ResultKind
    args_model: type[_Args]


CANONICAL_OPS: dict[str, CanonicalOp] = {
    op.name: op
    for op in (
        CanonicalOp("contact.lookup", OpKind.QUERY, ResultKind.OBJECT, ContactLookupArgs),
        CanonicalOp("journal.list", OpKind.QUERY, ResultKind.LIST, JournalListArgs),
        CanonicalOp("journal.get", OpKind.QUERY, ResultKind.OBJECT, JournalGetArgs),
        CanonicalOp("journal.create", OpKind.MUTATION, ResultKind.OBJECT, JournalCreateArgs),
    )
}


def get_op(op_name: str) -> CanonicalOp:
    """Look up a canonical op or raise UnknownOpError (grammar-cage reject)."""
    op = CANONICAL_OPS.get(op_name)
    if op is None:
        raise UnknownOpError(op_name)
    return op


def validate_args(op_name: str, raw: dict) -> _Args:
    """Validate raw (LLM-proposed) args against the canonical op's schema.

    This is load-bearing: it is the boundary between an LLM's output and a real
    provider call. Raises UnknownOpError for an unknown op, ArgValidationError
    for args that do not fit the schema.
    """
    op = get_op(op_name)
    try:
        return op.args_model.model_validate(raw or {})
    except ValidationError as e:
        raise ArgValidationError(op_name, _short(e)) from e


def _short(e: ValidationError) -> str:
    """Compact, stable one-line summary of a validation error (no LLM text)."""
    parts = []
    for err in e.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)
