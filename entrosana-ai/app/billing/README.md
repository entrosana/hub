# billing/

Family-based invoicing. Sibling discounts, multi-stage payment
plans, late-fee escalation.

The `family_id` column lets the billing engine aggregate siblings'
tuition into one parent-facing invoice. The discount + payment-plan
rules live in service-layer policy modules (not in the schema).

## Tables

- `billing_invoices` — number, family_id, amount_cents, currency,
  issued_on, due_on, `status ∈ {open, partially_paid, paid, voided}`,
  paid_at

## Endpoints

- `GET  /api/v1/billing/invoices?overdue_as_of=2026-05-01`
- `GET  /api/v1/billing/invoices?family_id=...`
- `POST /api/v1/billing/invoices`

## Planned

- `PaymentPlan` table for multi-stage invoices (instalment schedule)
- QR-bill (Swiss QR-Rechnung) PDF generation on issue
- Reconciliation against CashCtrl bank import: open → paid on match
