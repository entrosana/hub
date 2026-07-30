"""The one deterministic executor. Runs any provider from its pinned spec.

Given a validated canonical op + args and a :class:`~app.providers.spec.ProviderSpec`,
it builds a fully-resolved request (path template → params/body → auth headers),
sends it over the injected transport, and maps the response back to canonical shape.
Composite ``steps`` ops run sequentially: a step with ``when_arg`` only fires when
that arg is present, later steps consume earlier results via ``source: prev``, and
a resolution step that fires but finds nothing short-circuits to an EMPTY result
(never a silently unscoped query).

It is intentionally free of the two things that would break determinism/replay:
no clock, no randomness. Same (spec, op, args, transport) → same result, always.
The spec version is threaded into every result so the signed audit row pins exactly
which mapping ran. Failure is always loud: provider-signalled errors (HTTP-200
envelopes), truncated pagination, non-advancing cursors, unset secrets, and args
the binding cannot honor all raise instead of producing plausible-but-wrong data.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from app.core.config import settings
from app.providers.errors import (
    ConfirmationRequiredError,
    ExecutionError,
    IdempotencyRequiredError,
    UnsupportedOperationError,
)
from app.providers.spec import (
    AuthKind,
    AuthSpec,
    HttpBinding,
    ParamMap,
    ParamSource,
    ProviderSpec,
    ResponseMap,
)
from app.providers.transport import ProviderRequest, Transport
from app.providers.vocabulary import OpKind, ResultKind, get_op

_MAX_PAGES = 100  # pagination backstop — never loop unbounded on a bad cursor
_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

# Sentinel for a step that did not run (its when_arg was absent).
_SKIPPED = object()


def _fingerprint(value: Any) -> str:
    """SHA-256 over canonical JSON (sorted keys, no whitespace, no NaN).

    Deterministic by construction, so the same payload always fingerprints the same
    and a stored hash stays checkable. Non-JSON input fails loudly rather than
    producing a hash that cannot be reproduced.
    """

    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ).encode()
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive
        raise ExecutionError("provider result is not canonical JSON") from exc
    return hashlib.sha256(encoded).hexdigest()


class _EmptyShortCircuit(Exception):  # noqa: N818 — control-flow signal, not an error
    """A fired resolution step found nothing → the scoped result is empty."""


@dataclass(frozen=True, slots=True)
class CanonicalResult:
    op: str
    source: str  # provider name that produced this
    spec_version: str  # pinned spec version — goes into the signed audit row
    data: Any  # list[dict] | dict | None (per op.result kind)
    count: int  # rows for a list, 0/1 for an object
    raw: Any  # untouched provider response(s) — for audit/replay
    # Content fingerprints over canonical JSON. Recording these in the signed audit
    # row lets anyone later prove WHICH bytes were returned, not merely how many rows.
    data_sha256: str
    raw_sha256: str


class ProviderExecutor:
    """Executes canonical ops against one provider spec over one transport.

    ``credential_overrides`` maps settings-attribute names to per-tenant secret
    values (from the tenant's binding). Multi-tenant production MUST supply these:
    with only the global settings key, all tenants share one provider account and
    therefore one data pool (see ADR 0002 — per-tenant credentials).
    """

    def __init__(
        self,
        spec: ProviderSpec,
        transport: Transport,
        credential_overrides: dict[str, str] | None = None,
    ) -> None:
        self.spec = spec
        self.transport = transport
        self._credential_overrides = credential_overrides or {}

    async def execute(
        self,
        op_name: str,
        args: dict[str, Any],
        *,
        confirmed: bool = False,
        idempotency_key: str | None = None,
    ) -> CanonicalResult:
        op = get_op(op_name)  # canonical (raises UnknownOpError if not)
        binding = self.spec.operations.get(op_name)
        if binding is None:
            raise UnsupportedOperationError(self.spec.name, op_name)

        # A write is refused at the kernel boundary unless the caller confirmed it.
        if op.kind == OpKind.MUTATION and not confirmed:
            raise ConfirmationRequiredError(op_name)

        # If any binding declares an idempotency header, a key is mandatory — and it
        # must be header-safe, so a caller-supplied value cannot inject a second header.
        calls = binding.steps if binding.steps is not None else [binding.http]
        if any(c is not None and c.idempotency_header for c in calls):
            if not idempotency_key:
                raise IdempotencyRequiredError(op_name)
            if any(ord(ch) < 32 or ord(ch) == 127 for ch in idempotency_key):
                raise ExecutionError("idempotency_key contains control characters")

        try:
            if binding.steps is not None:
                self._reject_unconsumed_args(binding.steps, args, op_name)
                raw_pages, items = await self._run_steps(
                    binding.steps, args, op.result, op_name, idempotency_key
                )
            else:
                assert binding.http is not None
                self._reject_unconsumed_args([binding.http], args, op_name)
                raw_pages, items = await self._run_http(
                    binding.http, args, op.result, [], op_name, idempotency_key
                )
        except _EmptyShortCircuit:
            empty: Any = [] if op.result == ResultKind.LIST else None
            return CanonicalResult(
                op=op_name,
                source=self.spec.name,
                spec_version=self.spec.version,
                data=empty,
                count=0,
                raw=None,
                data_sha256=_fingerprint(empty),
                raw_sha256=_fingerprint(None),
            )

        if op.result == ResultKind.LIST:
            data: Any = items
            count = len(items)
            raw: Any = raw_pages if len(raw_pages) > 1 else raw_pages[0]
        else:
            obj = items[0] if items else None
            data = obj
            count = 0 if obj is None else 1
            raw = raw_pages[-1]
        return CanonicalResult(
            op=op_name,
            source=self.spec.name,
            spec_version=self.spec.version,
            data=data,
            count=count,
            raw=raw,
            data_sha256=_fingerprint(data),
            raw_sha256=_fingerprint(raw),
        )

    # ── composite steps ───────────────────────────────────────────────────

    async def _run_steps(
        self,
        steps: list[HttpBinding],
        args: dict[str, Any],
        result_kind: ResultKind,
        op_name: str,
        idempotency_key: str | None = None,
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        """Run resolution steps, then the final step whose response is the result.

        Semantics (deterministic, enforced here):
          * a step with ``when_arg`` runs only if that arg is non-None; skipped
            steps resolve to _SKIPPED (prev-params fall back or omit);
          * a fired resolution step with no result raises _EmptyShortCircuit —
            the caller asked for a scope that resolves to nothing, so the answer
            is EMPTY, never an unscoped query;
          * only the final step paginates / carries the op's result kind.
        """
        step_results: list[Any] = []
        all_raw: list[Any] = []
        for step in steps[:-1]:
            if step.when_arg and args.get(step.when_arg) is None:
                step_results.append(_SKIPPED)
                continue
            raw_pages, items = await self._run_http(
                step, args, ResultKind.OBJECT, step_results, op_name
            )
            all_raw.extend(raw_pages)
            obj = items[0] if items else None
            if obj is None:
                raise _EmptyShortCircuit(op_name)
            step_results.append(obj)

        raw_pages, items = await self._run_http(
            steps[-1], args, result_kind, step_results, op_name, idempotency_key
        )
        return all_raw + raw_pages, items

    # ── request building ──────────────────────────────────────────────────

    async def _run_http(
        self,
        http: HttpBinding,
        args: dict[str, Any],
        result_kind: ResultKind,
        step_results: list[Any],
        op_name: str,
        idempotency_key: str | None = None,
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        """Send the request (following pagination for lists); return (raw_pages, mapped_items)."""
        base = self._base_url()
        path = self._fill_path(http.path, args)
        params = self._resolve_params(http.query, args, step_results)
        body = self._resolve_params(http.body, args, step_results) or None
        headers = self._auth_headers(self.spec.auth)
        if http.idempotency_header and idempotency_key:
            headers = {**headers, http.idempotency_header: idempotency_key}

        raw_pages: list[Any] = []
        items: list[dict[str, Any]] = []
        cursor: Any = None
        for _ in range(_MAX_PAGES):
            call_params = dict(params)
            if cursor is not None and http.response.cursor_param:
                call_params[http.response.cursor_param] = cursor
            req = ProviderRequest(
                method=http.method,
                url=f"{base}{path}",
                path=path,
                headers=headers,
                params=call_params,
                json=body,
            )
            raw = await self.transport.send(req)
            self._check_envelope(raw, http.response, op_name)
            raw_pages.append(raw)
            items.extend(self._map_items(raw, http.response, result_kind))

            if result_kind != ResultKind.LIST or not http.response.next_cursor_path:
                cursor = None
                break
            next_cursor = _dig(raw, http.response.next_cursor_path)
            if not next_cursor:
                cursor = None
                break
            if next_cursor == cursor:
                # a non-advancing cursor would re-fetch the same page forever
                raise ExecutionError(
                    f"provider {self.spec.name!r}: {op_name} pagination cursor did not "
                    "advance — refusing to duplicate rows"
                )
            cursor = next_cursor
        if cursor:
            # loop exhausted _MAX_PAGES with more pages pending — the list is
            # incomplete and must not be signed as authoritative (fail loud).
            raise ExecutionError(
                f"provider {self.spec.name!r}: {op_name} exceeded {_MAX_PAGES} pages — "
                "refusing to return a truncated list"
            )
        return raw_pages, items

    def _check_envelope(self, raw: Any, rmap: ResponseMap, op_name: str) -> None:
        """HTTP-200 logical failures (e.g. CashCtrl ``success: false``) fail loud.

        Boolean-STRICT: only ``True``/``1``/the string ``"true"`` count as success —
        a provider sending ``"false"`` (string) must not pass a Python truthiness
        check and get its error body signed as an empty success.
        """
        if not rmap.success_path:
            return
        flag = _dig(raw, rmap.success_path)
        ok = flag is True or flag == 1 or (isinstance(flag, str) and flag.strip().lower() == "true")
        if ok:
            return
        msg = _dig(raw, rmap.error_message_path) if rmap.error_message_path else None
        raise ExecutionError(
            f"provider {self.spec.name!r}: {op_name} reported failure: {msg or 'no message'}"
        )

    def _reject_unconsumed_args(
        self, bindings: list[HttpBinding], args: dict[str, Any], op_name: str
    ) -> None:
        """A provided arg the binding(s) never send would silently widen the query
        (e.g. a contact filter that just disappears). Refuse instead."""
        consumed: set[str] = set()
        for http in bindings:
            consumed.update(_PLACEHOLDER.findall(http.path))
            if http.when_arg:
                consumed.add(http.when_arg)
            for pm in list(http.query.values()) + list(http.body.values()):
                if pm.arg:
                    consumed.add(pm.arg)
                if pm.fallback_arg:
                    consumed.add(pm.fallback_arg)
        unconsumed = {k for k, v in args.items() if v is not None} - consumed
        if unconsumed:
            raise ExecutionError(
                f"provider {self.spec.name!r}: {op_name} does not support "
                f"argument(s) {sorted(unconsumed)} — refusing to run the query unscoped"
            )

    def _base_url(self) -> str:
        """Resolve the provider base URL: per-tenant override first, then global
        settings. Fails CLOSED — an unset/non-http(s) base refuses the call (and a
        mis-pointed base_url_setting cannot leak an arbitrary settings value into
        request URLs or error text, because secrets don't start with http)."""
        raw = self._credential_overrides.get(self.spec.base_url_setting) or getattr(
            settings, self.spec.base_url_setting, ""
        )
        base = (raw or "").strip().rstrip("/") if isinstance(raw, str) else ""
        if not base.startswith(("http://", "https://")):
            raise ExecutionError(
                f"provider {self.spec.name!r}: base URL setting "
                f"{self.spec.base_url_setting!r} is not configured with an http(s) URL — "
                "refusing to send the request"
            )
        return base

    def _fill_path(self, template: str, args: dict[str, Any]) -> str:
        """Fill {arg} placeholders with the arg PERCENT-ENCODED as one path
        segment (quote with safe="") — an LLM-proposed value like '../admin',
        'x?evil=1' or one containing CR/LF cannot break out of its segment."""

        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            val = args.get(name)
            if val is None:
                raise ExecutionError(f"path {template!r} needs arg {name!r}")
            encoded = quote(str(val), safe="")
            if not encoded:
                raise ExecutionError(f"path {template!r} arg {name!r} is empty")
            return encoded

        return _PLACEHOLDER.sub(repl, template)

    def _resolve_params(
        self, mapping: dict[str, ParamMap], args: dict[str, Any], step_results: list[Any]
    ) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for field_name, pm in mapping.items():
            value, present = self._resolve_param(pm, args, step_results, field_name)
            if present:
                out[field_name] = value
        return out

    def _resolve_param(
        self, pm: ParamMap, args: dict[str, Any], step_results: list[Any], field_name: str
    ) -> tuple[Any, bool]:
        """Return (value, include?). Absent optional values are omitted."""
        if pm.source == ParamSource.CONST:
            return pm.const, True

        if pm.source == ParamSource.PREV:
            assert pm.step is not None and pm.field  # spec-validated
            if pm.step >= len(step_results):
                raise ExecutionError(
                    f"param {field_name!r} references step {pm.step} which has not run"
                )
            entry = step_results[pm.step]
            if entry is _SKIPPED:
                # resolution step didn't fire — fall back to a direct arg if declared
                if pm.fallback_arg is not None:
                    return _arg_value(args, pm.fallback_arg, pm.required, field_name)
                if pm.required:
                    raise ExecutionError(
                        f"param {field_name!r} requires step {pm.step}, which was skipped"
                    )
                return None, False
            value = entry.get(pm.field) if isinstance(entry, dict) else None
            if value is None:
                if pm.required:
                    raise ExecutionError(
                        f"param {field_name!r}: step {pm.step} result lacks {pm.field!r}"
                    )
                return None, False
            return value, True

        # source == ARG
        assert pm.arg is not None  # spec-validated
        return _arg_value(args, pm.arg, pm.required, field_name)

    def _auth_headers(self, auth: AuthSpec) -> dict[str, str]:
        if auth.kind == AuthKind.NONE:
            return {}
        if auth.kind == AuthKind.BEARER:
            return {"Authorization": f"Bearer {self._secret(auth.key_setting)}"}
        if auth.kind == AuthKind.API_KEY_HEADER:
            if not auth.header:
                raise ExecutionError(f"provider {self.spec.name!r}: api_key_header needs 'header'")
            return {auth.header: self._secret(auth.key_setting)}
        if auth.kind == AuthKind.BASIC:
            user = self._secret(auth.username_setting)
            pw = self._secret(auth.password_setting)
            token = base64.b64encode(f"{user}:{pw}".encode()).decode()
            return {"Authorization": f"Basic {token}"}
        # OAUTH2 and anything else: declared for planning, not executable yet.
        raise ExecutionError(f"provider {self.spec.name!r}: auth kind {auth.kind} not implemented")

    def _secret(self, setting_name: str | None) -> str:
        """Per-tenant override first, then global settings. Fails CLOSED: an unset
        or whitespace-only secret refuses the request rather than sending a blank
        credential (``"   "`` is truthy in Python — strip before deciding)."""
        if not setting_name:
            raise ExecutionError(f"provider {self.spec.name!r}: auth references no setting")
        raw = self._credential_overrides.get(setting_name) or getattr(settings, setting_name, "")
        val = raw.strip() if isinstance(raw, str) else ""
        if not val:
            raise ExecutionError(
                f"provider {self.spec.name!r}: secret {setting_name!r} is not configured — "
                "refusing to send an unauthenticated request"
            )
        return val

    # ── response mapping ────────────────────────────────────────────────────

    def _map_items(
        self, raw: Any, rmap: ResponseMap, result_kind: ResultKind
    ) -> list[dict[str, Any]]:
        """Unwrap the payload and remap provider fields → canonical fields.

        Returns a list in all cases (object results carry 0 or 1 item) so the
        caller can uniformly extend across pages.
        """
        if result_kind == ResultKind.LIST:
            payload = _dig(raw, rmap.list_path) if rmap.list_path else raw
            if payload is None:
                return []  # explicit null = no rows (common provider idiom)
            if not isinstance(payload, list):
                raise ExecutionError(
                    f"provider {self.spec.name!r}: list payload at "
                    f"{rmap.list_path!r} is not an array — refusing to sign a guess"
                )
            out: list[dict[str, Any]] = []
            for r in payload:
                if not isinstance(r, dict):
                    # silently dropping elements would sign an under-count as complete
                    raise ExecutionError(
                        f"provider {self.spec.name!r}: non-object element in list "
                        f"payload at {rmap.list_path!r} — refusing to sign a partial list"
                    )
                out.append(self._remap(r, rmap))
            return out

        payload = _dig(raw, rmap.item_path) if rmap.item_path else raw
        if not isinstance(payload, dict):
            return []
        return [self._remap(payload, rmap)]

    def _remap(self, item: dict[str, Any], rmap: ResponseMap) -> dict[str, Any]:
        if not rmap.fields:
            return item  # pass-through: provider already canonical-shaped
        return {canon: _dig(item, src) for canon, src in rmap.fields.items()}


# ── helpers ───────────────────────────────────────────────────────────────


def _arg_value(args: dict[str, Any], arg: str, required: bool, field_name: str) -> tuple[Any, bool]:
    value = args.get(arg)
    if value is None:
        if required:
            raise ExecutionError(f"param {field_name!r} requires arg {arg!r}")
        return None, False
    return value, True


def _dig(obj: Any, dotpath: str | None) -> Any:
    """Walk ``a.b.c`` through nested dicts. Missing segment → None."""
    if not dotpath:
        return obj
    cur = obj
    for seg in dotpath.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return None
    return cur
