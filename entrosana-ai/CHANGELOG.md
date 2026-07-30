# Changelog

All notable changes to entrosana-ai will be documented here.  Keep-a-changelog
format.  Semantic versioning.

## [Unreleased]

### Changed

- All domain models now inherit from `app.core.base.TenantBase` (UUID PK,
  indexed UUID `tenant_id`, `created_at`/`updated_at` timestamps). Per-module
  models dropped ~6 lines of boilerplate each and gained `updated_at`.
- Per-module repositories now compose `app.core.crud.list_for_tenant` +
  `create_for_tenant` + `get_for_tenant`; each module's `repository.py` only
  holds domain-specific queries (e.g. `list_overdue`, `find_by_postcode`,
  `list_by_kind`).
- Endpoint URLs now reflect resource names (e.g. `/identity/users`,
  `/accounting/entries`, `/admin/persons`) rather than `/identity/`.
- Module models carry domain-specific columns instead of the stub
  `name: str` placeholder (e.g. `accounting.Entry` has `amount_cents`,
  `currency`, `status`; `documents.Document` has `filename`, `mime_type`,
  `storage_uri`).
- `audit.AuditEvent` + `audit.DLMInteraction` migrated to TenantBase; chain
  verify now returns `(ok, n_events, first_bad_event_id: UUID | None)`.
- `app.core.dependencies.get_tenant_id` validates the `X-Tenant-Id` header
  as a UUID instead of an opaque string.
- Identity creation now optionally hashes a password through
  `app.core.security.hash_password` (bcrypt); the password hash is
  intentionally excluded from the audit `after` payload.

### Fixed

- `accounting_entrys` table-name typo → `accounting_entries`.
- `addresses_addresss` table-name typo → `addresses_records`.

### Added

- `app/core/crud.py` — shared tenant-scoped CRUD helpers.
- `app/core/base.py` — `TenantBase` / `GlobalBase` ORM mixins on
  `sqlalchemy.Uuid` (dialect-adapting: native UUID on Postgres,
  CHAR(32) on SQLite).
- `app/core/security.py` — bcrypt password-hash helpers, wired into
  optional `User.password_hash` on identity creation.
- Real audit-chain tests (`tests/test_audit_chain.py`): verify-intact,
  tamper-detect, tenant-isolation, GENESIS-anchor.
- `aiosqlite` dev dep + in-memory `db`/`client` fixtures in
  `tests/conftest.py`.
- DLM doctrine layer (intent routing): `app/dlm/base/{core,cashctrl,
  env_fingerprint,example_school,verify_replay}.py`,
  `app/dlm/{intent,demo_intent}.py`,
  `app/dlm/prompts/v0.1.0/intent_route.md`.
- `scripts/verify_audit_chain.py` — independent HMAC verifier for the
  audit JSONL log.
- `docs/AUDIT.md` + `docs/POC.md` — audit report + POC walkthrough.
- `docs/brand/logomark.svg` — brand asset.
- `app/cashctrl/fake.py` — fake CashCtrl adapter for tests.
- `uv.lock` for reproducible installs.

### Fixed (additional)

- `app/dlm/runner.py` now iterates `resp.content` blocks and only
  reads `.text` from `TextBlock` instances (skips tool-use / thinking /
  image blocks instead of crashing).
- `Dockerfile` builds with hatchling's package-discovery requirement
  (copies `app/` before `pip install -e .`).

## [0.0.1] - 2026-05-18

### Added

- Phase 0 architectural scaffold:
  - 14 capability modules (identity, accounting, admin, scheduling, contracts,
    expenses, taxes, signup, addresses, billing, documents, audit, dlm, cashctrl)
  - FastAPI app with module routers under `/api/v1`
  - SQLAlchemy 2 + Alembic + asyncpg
  - Pydantic v2 schemas
  - Celery + Redis for async jobs (OCR, payroll)
  - OpenTelemetry tracing hook
  - structlog structured logging
- DLM doctrine implementation:
  - `app/dlm/runner.py` -- deterministic LLM wrapper
  - `app/audit/service.py` -- signed HMAC chain
  - `app/audit/router.py` -- chain verification endpoint
- Docker + dev-stack (Postgres + Redis)
- GitLab CI: lint, test, build stages

### Not yet implemented

- Real business logic in any module (all stubs)
- CashCtrl integration (adapter exists; no real calls)
- DLM prompt bundles (directory exists; no prompts)
- Swiss e-signature integration in contracts
- Swissdec payroll format in taxes
- Tenant isolation enforcement at the SQL layer
- Authentication flows in identity
