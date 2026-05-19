# accounting/

GL entries, booking proposals, CashCtrl sync, amber-zone escalation queue.

The DLM reads source documents (`app/documents`) and emits booking
proposals here. Proposals start at `status='proposed'`; an accountant
must approve before they propagate to CashCtrl.

## Tables

- `accounting_entries` — proposed / approved / posted / voided GL lines

## Endpoints

- `GET  /api/v1/accounting/entries?status=proposed` — review queue
- `POST /api/v1/accounting/entries` — propose a new booking entry

## Planned

- `Approval` table tracking who approved which entry and when
- CashCtrl push: on `status -> posted`, call `app.cashctrl.client.create_entry`
- Amber-zone heuristic: low-confidence DLM outputs flagged for human review
