# documents/

Document ingestion (email + upload), OCR, classification.

The AI surface of the platform. Receipts and invoices come in
through this module; the DLM OCRs them, classifies them
(receipt vs invoice vs contract vs payslip vs ...) and routes
the extracted facts to the relevant module.

## Tables

- `documents_documents` — filename, mime_type, storage_uri,
  size_bytes, optional classification, `status ∈ {uploaded, ocr_pending,
  ocr_done, classified, archived}`

## Endpoints

- `GET  /api/v1/documents/?classification=receipt`
- `POST /api/v1/documents/` — register a freshly uploaded file

## Planned

- Pre-signed upload URLs to S3-compatible storage (Cloudflare R2 / MinIO)
- Celery worker: OCR (Tesseract or Claude Vision) → updates `status`
- DLM classification call → fills `classification`, opens cross-module flows
  (e.g. receipt → app/expenses, invoice → app/accounting)
