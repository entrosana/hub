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
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.providers.errors import ExecutionError, UnsupportedOperationError
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
from app.providers.vocabulary import ResultKind, get_op

_MAX_PAGES = 100  # pagination backstop — never loop unbounded on a bad cursor
_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

# Sentinel for a step that did not run (its when_arg was absent).
_SKIPPED = object()


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

    async def execute(self, op_name: str, args: dict[str, Any]) -> CanonicalResult:
        op = get_op(op_name)  # canonical (raises UnknownOpError if not)
        binding = self.spec.operations.get(op_name)
        if binding is None:
            raise UnsupportedOperationError(self.spec.name, op_name)

        try:
            if binding.steps is not None:
                self._reject_unconsumed_args(binding.steps, args, op_name)
                raw_pages, items = await self._run_steps(binding.steps, args, op.result, op_name)
            else:
                assert binding.http is not None
                self._reject_unconsumed_args([binding.http], args, op_name)
                raw_pages, items = await self._run_http(binding.http, args, op.result, [], op_name)
        except _EmptyShortCircuit:
            empty: Any = [] if op.result == ResultKind.LIST else None
            return CanonicalResult(
                op=op_name,
                source=self.spec.name,
                spec_version=self.spec.version,
                data=empty,
                count=0,
                raw=None,
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
        )

    # ── composite steps ───────────────────────────────────────────────────

    async def _run_steps(
        self,
        steps: list[HttpBinding],
        args: dict[str, Any],
        result_kind: ResultKind,
        op_name: str,
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

        raw_pages, items = await self._run_http(steps[-1], args, result_kind, step_results, op_name)
        return all_raw + raw_pages, items

    # ── request building ──────────────────────────────────────────────────

    async def _run_http(
        self,
        http: HttpBinding,
        args: dict[str, Any],
        result_kind: ResultKind,
        step_results: list[Any],
        op_name: str,
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        """Send the request (following pagination for lists); return (raw_pages, mapped_items)."""
        base = (getattr(settings, self.spec.base_url_setting, "") or "").rstrip("/")
        path = self._fill_path(http.path, args)
        params = self._resolve_params(http.query, args, step_results)
        body = self._resolve_params(http.body, args, step_results) or None
        headers = self._auth_headers(self.spec.auth)

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
        """HTTP-200 logical failures (e.g. CashCtrl ``success: false``) fail loud."""
        if not rmap.success_path:
            return
        if _dig(raw, rmap.success_path):
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

    def _fill_path(self, template: str, args: dict[str, Any]) -> str:
        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            val = args.get(name)
            if val is None:
                raise ExecutionError(f"path {template!r} needs arg {name!r}")
            return str(val)

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
        secret refuses the request rather than sending a blank credential."""
        if not setting_name:
            raise ExecutionError(f"provider {self.spec.name!r}: auth references no setting")
        val = self._credential_overrides.get(setting_name) or getattr(settings, setting_name, "")
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
            rows = payload if isinstance(payload, list) else []
            return [self._remap(r, rmap) for r in rows if isinstance(r, dict)]

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
