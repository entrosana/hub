"""Dispatcher — the seam that turns a routed intent into an executed, audited action.

    prose → route (gateway) → grammar cage (canonical vocab) → resolve tenant's
    provider → deterministic executor → signed DB audit rows + DLMInteraction row

This is provider-agnostic: the same path runs against CashCtrl, bexio, or any
backend the tenant is bound to (``registry.resolve``). Queries execute immediately;
mutations are NOT auto-applied — they return a preview to be confirmed (propose →
confirm; the confirm leg is the next increment, ADR 0002).

The dispatcher OWNS persistence (it commits), because the audit contract is
ordering-sensitive:

  * queries are two-phase: a signed ``query.requested`` row is COMMITTED *before*
    the provider is called, then ``query.executed`` + the DLMInteraction row are
    committed after. An executed read therefore always has at least one committed
    signed record, even if the post-execution write fails (adversarial finding);
  * mutation previews persist their provenance (``mutation.proposed`` + a
    DLMInteraction row) — an LLM-proposed financial write is never untraceable —
    while writing nothing else and executing nothing.

Doctrine guardrails honored here:
  * all LLM access stays behind ``DLMGateway`` (temperature 0, pinned);
  * the LLM only proposes — args are validated against the cage before any call;
  * the provider/DB is the source of fact; every executed query is signed, and the
    signed row pins the provider + spec version that produced it (replayability).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import service as audit
from app.core import metrics
from app.core.auth import Principal
from app.core.config import settings
from app.dlm.gateway import DLMGateway
from app.dlm.gateway import gateway as default_gateway
from app.dlm.intent import ClaudeRouter
from app.providers.errors import UnsupportedOperationError
from app.providers.registry import get_registry
from app.providers.transport import HttpxTransport, Transport
from app.providers.vocabulary import OpKind, get_op, validate_args


@dataclass(frozen=True, slots=True)
class AssistantResult:
    tool: str
    args: dict[str, Any]
    kind: str  # "query" | "mutation"
    executed: bool  # False ⇒ mutation preview awaiting confirmation
    count: int
    source: str  # provider name that produced (or would produce) the result
    intent_hash: str
    result: Any = None  # canonical data (list | object | None); None for a preview
    summary: str = ""  # human-readable one-liner (used for mutation previews)


def _router_versions(gw: DLMGateway) -> tuple[str, str]:
    """Model/prompt provenance for the DLMInteraction row.

    The MockRouter is deterministic regex (no model); the ClaudeRouter uses the
    pinned model/prompt. Either way the row pins *which* router produced the call.
    """
    if isinstance(gw.router, ClaudeRouter):
        return settings.dlm_model_version, settings.dlm_prompt_version
    return "mock-router", "regex-v1"


async def dispatch_query(
    session: AsyncSession,
    principal: Principal,
    user_input: str,
    *,
    gateway: DLMGateway | None = None,
    transport: Transport | None = None,
) -> AssistantResult:
    """Route + validate + (for queries) execute against the tenant's provider.

    Commits the session (see module docstring — the audit contract requires it).
    Raises the provider layer's typed errors (UnknownOpError / ArgValidationError /
    UnknownProviderError / UnsupportedOperationError / ExecutionError); the
    endpoint maps them to HTTP.
    """
    gw = gateway or default_gateway
    registry = get_registry()

    routed = await gw.route_intent(user_input)
    op = get_op(routed.tool)  # grammar cage — canonical op only
    vargs = validate_args(routed.tool, routed.args)  # grammar cage — typed args
    args_out = vargs.model_dump(exclude_none=True)

    # Resolve + capability-check for BOTH kinds, so a misconfigured tenant or an
    # incapable provider fails as loudly on a mutation preview as on a read.
    spec = registry.resolve(principal.tenant_id)  # raises UnknownProviderError
    if not spec.supports(routed.tool):
        raise UnsupportedOperationError(spec.name, routed.tool)
    model_version, prompt_version = _router_versions(gw)

    def _dlm_kwargs() -> dict[str, Any]:
        return {
            "tenant_id": principal.tenant_id,
            "input_payload": {
                "user_input": user_input,
                "normalized": routed.canonical.normalized,
            },
            "runner_result": {
                "output": json.dumps({"tool": routed.tool, "args": args_out}, sort_keys=True),
                "model_version": model_version,
                "prompt_version": prompt_version,
                "retrieval_keys": [],
            },
        }

    base_after = {
        "tool": routed.tool,
        "args": args_out,
        "intent_hash": routed.canonical.intent_hash,
        "provider": spec.name,
        "spec_version": spec.version,
    }

    # Mutations never auto-apply — but the PROPOSAL is signed provenance: an
    # LLM-proposed financial write must be traceable even if never confirmed.
    if op.kind == OpKind.MUTATION:
        event = await audit.record(
            session,
            tenant_id=principal.tenant_id,
            actor_id=str(principal.user_id),
            action="mutation.proposed",
            target_type="accounting.mutation",
            target_id=routed.tool,
            after=base_after,
        )
        await audit.record_dlm(session, audit_event_id=event.id, **_dlm_kwargs())
        await session.commit()
        result = AssistantResult(
            tool=routed.tool,
            args=args_out,
            kind="mutation",
            executed=False,
            count=0,
            source=spec.name,
            intent_hash=routed.canonical.intent_hash,
            result=None,
            summary=_preview_summary(routed.tool, args_out),
        )
        metrics.observe_dlm(
            tool=routed.tool,
            kind="mutation",
            executed=False,
            tokens_in=routed.tokens_in,
            tokens_out=routed.tokens_out,
        )
        return result

    # Query path, phase 1 — commit the signed intent BEFORE touching the provider,
    # so an executed read can never end up with zero committed audit trail.
    await audit.record(
        session,
        tenant_id=principal.tenant_id,
        actor_id=str(principal.user_id),
        action="query.requested",
        target_type="accounting.query",
        target_id=routed.tool,
        after=base_after,
    )
    await session.commit()

    # Phase 2 — execute against the resolved provider (source of fact).
    transport = transport or HttpxTransport()
    executor = await registry.executor_for_tenant(principal.tenant_id, transport, session=session)
    try:
        cres = await executor.execute(routed.tool, vargs.model_dump())
    except Exception:
        metrics.observe_provider_call(spec.name, routed.tool, "error")
        raise
    metrics.observe_provider_call(spec.name, routed.tool, "success")

    # Phase 3 — sign the outcome + the pinned DLMInteraction row (M4).
    event = await audit.record(
        session,
        tenant_id=principal.tenant_id,
        actor_id=str(principal.user_id),
        action="query.executed",
        target_type="accounting.query",
        target_id=routed.tool,
        after={
            **base_after,
            "result_count": cres.count,
            "source": cres.source,
            "spec_version": cres.spec_version,
        },
    )
    await audit.record_dlm(session, audit_event_id=event.id, **_dlm_kwargs())
    await session.commit()

    result = AssistantResult(
        tool=routed.tool,
        args=args_out,
        kind="query",
        executed=True,
        count=cres.count,
        source=cres.source,
        intent_hash=routed.canonical.intent_hash,
        result=cres.data,
        summary="",
    )
    metrics.observe_dlm(
        tool=routed.tool,
        kind="query",
        executed=True,
        tokens_in=routed.tokens_in,
        tokens_out=routed.tokens_out,
    )
    return result


def _preview_summary(tool: str, args: dict[str, Any]) -> str:
    """Stable, human-readable one-liner for a mutation preview (no LLM prose)."""
    parts = ", ".join(f"{k}={v}" for k, v in sorted(args.items()))
    return f"{tool} — {parts}" if parts else tool
