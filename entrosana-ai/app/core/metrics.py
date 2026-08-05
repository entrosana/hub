"""Prometheus metrics and structured business-metric observations."""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)

from app.core.config import settings
from app.core.logging import log

registry = CollectorRegistry()

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests.",
    ["method", "route", "status"],
    registry=registry,
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "route"],
    registry=registry,
)
dlm_intents_total = Counter(
    "dlm_intents_total",
    "Total routed DLM intents.",
    ["tool", "kind", "executed"],
    registry=registry,
)
dlm_tokens_total = Counter(
    "dlm_tokens_total",
    "Total DLM tokens.",
    ["direction"],
    registry=registry,
)
provider_calls_total = Counter(
    "provider_calls_total",
    "Total provider calls.",
    ["provider", "op", "outcome"],
    registry=registry,
)
audit_events_total = Counter(
    "audit_events_total",
    "Total appended audit events.",
    ["action"],
    registry=registry,
)


def observe_dlm(
    tool: str,
    kind: str,
    executed: bool,
    tokens_in: int,
    tokens_out: int,
) -> None:
    """Record a routed DLM intent and its token usage."""
    if not settings.metrics_enabled:
        return
    dlm_intents_total.labels(tool=tool, kind=kind, executed=str(executed).lower()).inc()
    dlm_tokens_total.labels(direction="in").inc(tokens_in)
    dlm_tokens_total.labels(direction="out").inc(tokens_out)
    log.info(
        "dlm metric observed",
        tool=tool,
        kind=kind,
        executed=executed,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )


def observe_provider_call(provider: str, op: str, outcome: str) -> None:
    """Record a provider call outcome."""
    if not settings.metrics_enabled:
        return
    provider_calls_total.labels(provider=provider, op=op, outcome=outcome).inc()
    log.info("provider metric observed", provider=provider, op=op, outcome=outcome)


def observe_audit(action: str) -> None:
    """Record an appended audit event."""
    if not settings.metrics_enabled:
        return
    audit_events_total.labels(action=action).inc()
    log.info("audit metric observed", action=action)


def render_latest() -> tuple[bytes, str]:
    """Render the current application metrics for a Prometheus scrape."""
    return generate_latest(registry), CONTENT_TYPE_LATEST
