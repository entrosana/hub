"""Health probe endpoint tests."""

import pytest

pytestmark = pytest.mark.anyio


async def test_health_probes_report_process_and_database_status(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}

    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}

    response = await client.get("/health/startup")
    assert response.status_code == 200
    assert response.json() == {"status": "started"}


async def test_readiness_probe_does_not_propagate_database_failure(client, monkeypatch):
    async def fail_database_check():
        raise RuntimeError("database secret should not leak")

    monkeypatch.setattr("app.main._check_database", fail_database_check)

    response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "detail": "database unavailable",
    }
