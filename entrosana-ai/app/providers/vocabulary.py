"""Canonical, domain-neutral operation vocabulary.

This is the *only* thing the intent router (Mock or Claude) is allowed to emit,
and the *only* contract a provider spec binds against. It is deliberately small
and stable so a small offline model can be grammar-caged onto it: the model picks
one ``name`` from ``CANONICAL_OPS`` and fills the matching ``args_model``; nothing
else is accepted.

The kernel ships **no operations of its own**. A domain pack (for example
``app.providers.domains.accounting``) declares its ops and registers them through
:func:`register_ops`; ``app/providers/__init__.py`` imports the packs that are
active in this deployment. Swapping or adding a domain therefore touches one
module, never the executor, spec loader, registry, or dispatcher.

Design rules:
  * Op names are ``<object>.<verb>`` — never a vendor name.
  * Arg models set ``extra="forbid"`` so a hallucinated argument is rejected before
    any provider call (the cage). Args are canonical; the per-provider spec maps
    them to that backend's HTTP params.
  * Dates are ISO ``YYYY-MM-DD`` (normalization already converts Swiss DMY upstream).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from app.providers.errors import ArgValidationError, SpecError, UnknownOpError

# Reusable constrained scalars. These are value shapes, not domain vocabulary, so
# they stay in the kernel where every domain pack can use them.

# ISO calendar date, e.g. "2026-05-01". Validated shape only (not calendar-correct);
# the provider is the source of fact for what the date actually resolves to.
IsoDate = Annotated[str, StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}$")]

# Audit-grade money: a plain decimal string with up to 2 fraction digits.
# Rejects "", scientific notation ("1e10"), padding (" 1.00 "), and floats
# (type is str) — a signed mutation proposal never carries a malformed amount.
MoneyStr = Annotated[str, StringConstraints(pattern=r"^-?\d{1,12}(\.\d{1,2})?$")]

# ``<object>.<verb>``, lowercase, no vendor names.
_OP_NAME = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")


class OpKind(str, Enum):
    QUERY = "query"  # reads; safe to execute immediately
    MUTATION = "mutation"  # writes; must go through propose → confirm


class ResultKind(str, Enum):
    OBJECT = "object"  # single object, or None if not found
    LIST = "list"  # list of objects (possibly empty)


class CanonicalArgs(BaseModel):
    """Base for all arg models: reject unknown keys so an LLM cannot smuggle in
    an argument the executor never validated."""

    model_config = ConfigDict(extra="forbid")


# Historical name, kept so existing domain modules and tests keep importing cleanly.
_Args = CanonicalArgs


@dataclass(frozen=True, slots=True)
class CanonicalOp:
    name: str
    kind: OpKind
    result: ResultKind
    args_model: type[CanonicalArgs]


# ── canonical op registry ─────────────────────────────────────────────────
#
# Populated by domain packs at import time. Readers hold a reference to this dict
# (spec.py, pathfinder.py), so registration mutates it IN PLACE and never rebinds.

CANONICAL_OPS: dict[str, CanonicalOp] = {}


def register_ops(*ops: CanonicalOp) -> None:
    """Add ops to the canonical vocabulary.

    Rejects malformed names and silent redefinition: two packs claiming the same
    op would make the grammar cage ambiguous, and whichever imported last would
    quietly win.
    """

    for op in ops:
        if not _OP_NAME.fullmatch(op.name):
            raise SpecError(f"canonical op {op.name!r} must be a dotted lowercase <object>.<verb>")
        existing = CANONICAL_OPS.get(op.name)
        if existing is not None and existing is not op:
            raise SpecError(f"canonical op {op.name!r} is already registered")
        CANONICAL_OPS[op.name] = op


def registered_ops() -> tuple[str, ...]:
    """Op names currently in the vocabulary, sorted — for diagnostics and tests."""

    return tuple(sorted(CANONICAL_OPS))


def get_op(op_name: str) -> CanonicalOp:
    """Look up a canonical op or raise UnknownOpError (grammar-cage reject)."""
    op = CANONICAL_OPS.get(op_name)
    if op is None:
        raise UnknownOpError(op_name)
    return op


def validate_args(op_name: str, raw: dict) -> CanonicalArgs:
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
