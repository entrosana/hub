"""Async payroll calculation.  Triggered monthly by taxes/scheduler.py."""

from app.tasks import celery_app


@celery_app.task(name="entrosana.taxes.payroll_calc")
def calculate_payroll(tenant_id: str, period: str) -> dict:
    """Stub.  Real impl: Swissdec-format payroll calc + source-tax tables."""
    return {"tenant_id": tenant_id, "period": period, "status": "queued"}
