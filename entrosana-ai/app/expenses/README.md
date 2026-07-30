# expenses/

Expense submission, approval workflow, reimbursement payout.

An expense links to a receipt document (`receipt_document_id` →
`app/documents`) which the DLM OCRs to pre-fill `amount_cents`
and `description` for the human review queue.

## Tables

- `expenses_expenses` — `status ∈ {submitted, approved, paid, rejected}`,
  amount_cents, currency, optional receipt link

## Endpoints

- `GET  /api/v1/expenses/?pending=true` — approval queue
- `POST /api/v1/expenses/` — submit a new expense

## Planned

- Approval workflow with role check (only staff with `expenses.approver` role)
- Push approved expenses to `app/accounting` as proposed entries
- Reimbursement payout (SEPA file generation or CashCtrl payment run)
