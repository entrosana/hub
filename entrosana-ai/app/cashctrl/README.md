# cashctrl/

Thin adapter to CashCtrl's REST API.  entrosana augments CashCtrl, never
replaces it.

Operations supported (Phase 0 scaffold):
- `journals.list()` / `.create()` — GL entries
- `documents.upload()` — invoice + receipt sync
- `webhooks.handle()` — receive booking-confirmation events from CashCtrl

API docs: https://app.cashctrl.com/api/v1
