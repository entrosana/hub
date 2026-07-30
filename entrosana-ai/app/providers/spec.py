"""Declarative provider spec — the adapter *is* this data.

A provider (CashCtrl, bexio, …) is described by a YAML file under ``specs/``, not
by hand-written Python. One deterministic executor (``app.providers.executor``)
runs every spec. The spec pins, per canonical op:

  * the HTTP binding — method, path template, how canonical args map to query/body
  * the response mapping — how the backend's JSON maps back to canonical fields
  * auth — *by reference to a settings attribute*, never an inline secret

Secrets never live in the spec (it is committed to git): ``base_url_setting`` and
the ``*_setting`` auth fields name attributes on ``app.core.config.settings``.

Composite operations are declared as ``steps``: a sequence of HTTP bindings run in
order, where later steps can consume earlier results (``source: prev``). A step
with ``when_arg`` only runs when that canonical arg is present — e.g. resolve a
contact name to an id first, then list its entries (see ADR 0002).
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.providers.errors import SpecError
from app.providers.vocabulary import CANONICAL_OPS

SPECS_DIR = Path(__file__).parent / "specs"


class AuthKind(str, Enum):
    NONE = "none"
    BEARER = "bearer"  # Authorization: Bearer <key>
    API_KEY_HEADER = "api_key_header"  # <header>: <key>
    BASIC = "basic"  # HTTP Basic (username:password)
    OAUTH2 = "oauth2"  # declared for planning; execution not yet wired


class AuthSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: AuthKind = AuthKind.NONE
    key_setting: str | None = None  # settings attr holding the token/key
    header: str | None = None  # header name for api_key_header
    username_setting: str | None = None  # settings attr (basic)
    password_setting: str | None = None  # settings attr (basic)


class ParamSource(str, Enum):
    ARG = "arg"  # value taken from a validated canonical arg
    CONST = "const"  # literal constant baked into the spec
    PREV = "prev"  # value taken from a previous step's result (composite ops)


class ParamMap(BaseModel):
    """How one request field (query param or body field) gets its value."""

    model_config = ConfigDict(extra="forbid")
    source: ParamSource = ParamSource.ARG
    arg: str | None = None  # canonical arg name  (source=arg)
    const: Any = None  # literal value       (source=const)
    step: int | None = None  # prior step index    (source=prev)
    field: str | None = None  # field in prior result (source=prev)
    # source=prev only: when the referenced step was SKIPPED (its when_arg was
    # absent), take the value from this canonical arg instead — lets one request
    # field accept either a resolved value or a directly-supplied arg.
    fallback_arg: str | None = None
    required: bool = False  # omit from request if the arg is absent & not required

    @model_validator(mode="after")
    def _coherent(self) -> ParamMap:
        if self.source == ParamSource.ARG and not self.arg:
            raise ValueError("param source 'arg' needs 'arg'")
        if self.source == ParamSource.PREV and (self.step is None or not self.field):
            raise ValueError("param source 'prev' needs 'step' and 'field'")
        if self.fallback_arg and self.source != ParamSource.PREV:
            raise ValueError("'fallback_arg' is only valid with source 'prev'")
        return self


class ResponseMap(BaseModel):
    """How a backend response maps to canonical shape."""

    model_config = ConfigDict(extra="forbid")
    # dot-path to the payload of interest (before field remap):
    list_path: str | None = None  # array location for list results
    item_path: str | None = None  # object location for object results
    # canonical_field -> provider dot-path (relative to each item / the object).
    # Empty ⇒ pass the item through unchanged.
    fields: dict[str, str] = {}
    # optional cursor pagination
    next_cursor_path: str | None = None
    cursor_param: str | None = None
    # optional error envelope: some APIs (CashCtrl) signal logical failure inside
    # an HTTP-200 body. If success_path is set and does not resolve to a truthy
    # value, the executor raises instead of signing an empty result as authoritative.
    success_path: str | None = None
    error_message_path: str | None = None

    @model_validator(mode="after")
    def _cursor_pair(self) -> ResponseMap:
        if bool(self.next_cursor_path) != bool(self.cursor_param):
            raise ValueError("next_cursor_path and cursor_param must be set together")
        return self


class HttpBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str  # may contain {arg} placeholders
    query: dict[str, ParamMap] = {}
    body: dict[str, ParamMap] = {}
    response: ResponseMap = ResponseMap()
    # steps only: run this step ONLY when the named canonical arg is present.
    # Skipped steps yield nothing; prev-params referencing them fall back or omit.
    when_arg: str | None = None

    # When set, this call carries the caller's idempotency key in the named header
    # and the executor refuses to run without one.
    idempotency_header: str | None = None

    @model_validator(mode="after")
    def _valid_idempotency_header(self) -> HttpBinding:
        if self.idempotency_header is not None and not re.fullmatch(
            r"[!#$%&\'*+\-.^_`|~0-9A-Za-z]+", self.idempotency_header
        ):
            raise ValueError("idempotency_header is not a valid HTTP header name")
        return self


class OperationBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    http: HttpBinding | None = None
    steps: list[HttpBinding] | None = None  # composite: sequential, last step = result

    @model_validator(mode="after")
    def _exactly_one(self) -> OperationBinding:
        if bool(self.http) == bool(self.steps):
            raise ValueError("operation needs exactly one of 'http' or 'steps'")
        if self.steps is not None and len(self.steps) < 2:
            raise ValueError("'steps' needs at least 2 steps (use 'http' for one)")
        if self.steps is not None and self.steps[-1].when_arg:
            raise ValueError("the final step cannot be conditional (when_arg)")
        return self


class ProviderSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str
    base_url_setting: str  # settings attr with the API base URL
    auth: AuthSpec = AuthSpec()
    operations: dict[str, OperationBinding]

    @model_validator(mode="after")
    def _known_ops(self) -> ProviderSpec:
        unknown = set(self.operations) - set(CANONICAL_OPS)
        if unknown:
            raise ValueError(f"spec {self.name!r} binds non-canonical op(s): {sorted(unknown)}")
        return self

    def supports(self, op_name: str) -> bool:
        return op_name in self.operations

    @property
    def capabilities(self) -> set[str]:
        """Canonical ops this provider implements (present ⇒ capable)."""
        return set(self.operations)


def load_spec(path: Path) -> ProviderSpec:
    """Parse + validate one provider spec YAML file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as e:
        raise SpecError(f"cannot read spec {path}: {e}") from e
    if not isinstance(raw, dict):
        raise SpecError(f"spec {path} is not a mapping")
    try:
        return ProviderSpec.model_validate(raw)
    except ValidationError as e:
        raise SpecError(f"invalid spec {path}: {e}") from e


def load_all(specs_dir: Path = SPECS_DIR) -> dict[str, ProviderSpec]:
    """Load every ``*.yaml`` spec in a directory, keyed by provider name.

    The filename stem must equal the spec's ``name`` (so the registry can find a
    provider by name without opening every file).
    """
    out: dict[str, ProviderSpec] = {}
    if not specs_dir.is_dir():
        return out
    for path in sorted(specs_dir.glob("*.yaml")):
        spec = load_spec(path)
        if spec.name != path.stem:
            raise SpecError(f"spec name {spec.name!r} does not match filename {path.stem!r}")
        out[spec.name] = spec
    return out
