"""Tests for application metrics and the public scrape endpoint."""

from __future__ import annotations

import secrets
from uuid import uuid4

import pytest

from app.core import metrics
from app.core.config import settings
from app.identity import service as identity_service

pytestmark = pytest.mark.anyio


async def _admin_token(db, client):
    password = secrets.token_urlsafe(24)
    user = await identity_service.create_user(
        db,
        tenant_id=uuid4(),
        actor_id="metrics-test",
        name="Metrics Test",
        email=f"{uuid4()}@example.com",
        password=password,
        role="admin",
    )
    await db.commit()
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_metrics_endpoint_exposes_application_metrics(client):
    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "http_requests_total" in body
    assert "dlm_intents_total" in body
    assert "provider_calls_total" in body
    assert "audit_events_total" in body


async def test_authenticated_request_is_counted_with_route_template(db, client):
    headers = await _admin_token(db, client)
    response = await client.get("/api/v1/identity/users", headers=headers)
    assert response.status_code == 200

    sample = metrics.registry.get_sample_value(
        "http_requests_total",
        {"method": "GET", "route": "/api/v1/identity/users", "status": "200"},
    )
    assert sample is not None
    assert sample >= 1
    assert str(uuid4()) not in client.base_url.path


def test_business_metric_helpers_increment_counters(monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", True)
    before_intents = (
        metrics.registry.get_sample_value(
            "dlm_intents_total",
            {"tool": "journal.list", "kind": "query", "executed": "true"},
        )
        or 0
    )
    before_in = metrics.registry.get_sample_value("dlm_tokens_total", {"direction": "in"}) or 0
    before_provider = (
        metrics.registry.get_sample_value(
            "provider_calls_total",
            {"provider": "cashctrl", "op": "journal.list", "outcome": "success"},
        )
        or 0
    )
    before_audit = (
        metrics.registry.get_sample_value("audit_events_total", {"action": "query.executed"}) or 0
    )

    metrics.observe_dlm("journal.list", "query", True, 3, 5)
    metrics.observe_provider_call("cashctrl", "journal.list", "success")
    metrics.observe_audit("query.executed")

    assert (
        metrics.registry.get_sample_value(
            "dlm_intents_total",
            {"tool": "journal.list", "kind": "query", "executed": "true"},
        )
        == before_intents + 1
    )
    assert (
        metrics.registry.get_sample_value("dlm_tokens_total", {"direction": "in"}) == before_in + 3
    )
    assert (
        metrics.registry.get_sample_value(
            "provider_calls_total",
            {"provider": "cashctrl", "op": "journal.list", "outcome": "success"},
        )
        == before_provider + 1
    )
    assert (
        metrics.registry.get_sample_value("audit_events_total", {"action": "query.executed"})
        == before_audit + 1
    )


async def test_metrics_can_be_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "metrics_enabled", False)

    response = await client.get("/metrics")

    assert response.status_code == 404
