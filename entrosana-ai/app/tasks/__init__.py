"""Celery task queue.  Anything taking >1s goes here."""
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "entrosana",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Zurich",
    enable_utc=True,
)

# Import task modules so Celery sees them
from app.tasks import document_ocr, payroll_calc  # noqa: F401,E402
