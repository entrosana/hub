"""DLMGateway — the single entry point for audit-grade DLM operations.

All LLM calls, intent routing, transduction, and verification flow through
this facade.  Direct use of ``anthropic.Anthropic()`` or ad-hoc routers
outside this module is forbidden by project doctrine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Self

from app.dlm.base.core import Agent, Decision, DLM, Features, Verifier, audit_chain
from app.dlm.base.env_fingerprint import RuntimeFingerprint
from app.dlm.intent import ClaudeRouter, IntentRouter, MockRouter, ToolCall as IntentToolCall
from app.dlm.normalize import CanonicalIntent, canonical_intent


@dataclass(frozen=True, slots=True)
class RoutedIntent:
    """Intent after normalization and routing (s1 in the Kronos hierarchy)."""

    canonical: CanonicalIntent
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True, slots=True)
class QueryAuditPayload:
    """Audit row fields for an intent → CashCtrl query (demo / POC path)."""

    ts: str
    tenant_id: str
    actor_id: str
    action: str
    user_input: str
    normalized_input: str
    intent_hash: str
    tool_call: dict[str, Any]
    result_count: int
    provenance: str
    source: str
    env_fp: str


class DLMGateway:
    """Process-wide singleton for DLM pipeline operations."""

    _instance: ClassVar[DLMGateway | None] = None

    def __init__(self, router: IntentRouter | None = None) -> None:
        self._router = router or MockRouter()
        self._env_fp: RuntimeFingerprint | None = None

    @classmethod
    def instance(cls, router: IntentRouter | None = None) -> Self:
        if cls._instance is None:
            cls._instance = cls(router)
        elif router is not None:
            cls._instance._router = router
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Clear the singleton — for tests only."""
        cls._instance = None

    @property
    def router(self) -> IntentRouter:
        return self._router

    def capture_env(self, code_files: list | None = None) -> RuntimeFingerprint:
        """Pin runtime + source revision (Kronos ``MODEL_REVISION`` equivalent)."""
        if code_files is None:
            root = Path(__file__).resolve().parent
            code_files = [
                root / "gateway.py",
                root / "normalize.py",
                root / "runner.py",
                root / "intent.py",
                root / "base" / "core.py",
            ]
        self._env_fp = RuntimeFingerprint.capture(code_files)
        return self._env_fp

    @property
    def env_fingerprint(self) -> str:
        if self._env_fp is None:
            self.capture_env()
        assert self._env_fp is not None
        return self._env_fp.fp

    def normalize(self, user_input: str) -> CanonicalIntent:
        return canonical_intent(user_input)

    async def route_intent(self, user_input: str) -> RoutedIntent:
        """Normalize prose → structured tool call (s1 only)."""
        ci = self.normalize(user_input)
        tc: IntentToolCall = await self._router.route(ci.normalized)
        return RoutedIntent(
            canonical=ci,
            tool=tc.tool,
            args=dict(sorted(tc.args.items())) if tc.args else {},
        )

    async def run_llm(
        self,
        prompt_name: str,
        input_data: dict[str, Any],
        *,
        retrieval_keys: list[str] | None = None,
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Pinned LLM call — delegates to ``runner.run`` (temperature 0)."""
        from app.dlm.runner import run

        return await run(
            prompt_name,
            input_data,
            retrieval_keys=retrieval_keys,
            max_tokens=max_tokens,
        )

    def propose(self, agent: Agent, features: Features) -> Decision:
        """Run the deterministic transducer and sign (s2 under pinned grammar)."""
        return agent.propose(features)

    def verify(
        self,
        decision: Decision,
        *,
        features: Features,
        dlm: DLM,
        verifier: Verifier,
    ) -> dict[str, tuple[bool, str]]:
        return audit_chain(decision, features=features, dlm=dlm, verifier=verifier)

    def build_query_audit(
        self,
        routed: RoutedIntent,
        *,
        result_count: int,
        tenant_id: str,
        actor_id: str,
        source: str = "cashctrl",
    ) -> QueryAuditPayload:
        return QueryAuditPayload(
            ts=datetime.now(UTC).isoformat(timespec="seconds"),
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="query.executed",
            user_input=routed.canonical.raw,
            normalized_input=routed.canonical.normalized,
            intent_hash=routed.canonical.intent_hash,
            tool_call={"tool": routed.tool, "args": routed.args},
            result_count=result_count,
            provenance="record",
            source=source,
            env_fp=self.env_fingerprint,
        )

    @classmethod
    def for_claude(cls) -> Self:
        return cls.instance(ClaudeRouter())

    @classmethod
    def for_mock(cls) -> Self:
        return cls.instance(MockRouter())


# Module-level default — import ``gateway`` for the production singleton.
gateway = DLMGateway.instance()
