"""Request middleware for cross-cutting request context."""

import time
from uuid import uuid4

import structlog
from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core import metrics
from app.core.config import settings


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Bind a request ID and active trace context to structured logs."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID")
        if not request_id or not request_id.strip():
            request_id = uuid4().hex

        structlog.contextvars.bind_contextvars(request_id=request_id)
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            structlog.contextvars.bind_contextvars(
                trace_id=format(span_context.trace_id, "032x"),
                span_id=format(span_context.span_id, "016x"),
            )

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()


class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request count and duration using matched route templates."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not settings.metrics_enabled:
            return await call_next(request)

        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            route_template = getattr(route, "path", None) or "unmatched"
            metrics.http_requests_total.labels(
                method=request.method,
                route=route_template,
                status=str(status_code),
            ).inc()
            metrics.http_request_duration_seconds.labels(
                method=request.method,
                route=route_template,
            ).observe(time.perf_counter() - started)
