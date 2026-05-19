"""Async OCR job.  Triggered by documents/service.py."""

from app.tasks import celery_app


@celery_app.task(name="entrosana.documents.ocr")
def ocr_document(document_id: int) -> dict:
    """Stub.  Real impl: pull document blob, run Tesseract/Claude vision, store result."""
    return {"document_id": document_id, "status": "queued"}
