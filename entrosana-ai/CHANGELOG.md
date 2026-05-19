# Changelog

All notable changes to entrosana-ai will be documented here.  Keep-a-changelog
format.  Semantic versioning.

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
