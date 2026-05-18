# entrosana-ai

> Audit-grade AI for back-office work.  Swiss-hosted, deterministic, built on CashCtrl.

This is the API monolith powering [entrosana.com](https://entrosana.com).
A FastAPI app organized into capability modules (accounting, admin, scheduling,
contracts, expenses, taxes, signup, addresses, billing, documents) that all
write through a single signed audit trail.

## Why deterministic

A regular LLM is creative.  For back-office work — bookkeeping, payroll, contracts
— consistency and auditability matter more than novelty.  Every entrosana action
runs through a **DLM (Deterministic Language Model)**:

- `temperature 0`
- pinned model version
- pinned prompt version
- deterministic retrieval order
- signed audit trail per interaction

Same input → same output.  Always.  Audit-grade.

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).  TL;DR:

```
            ┌─────────────────────────────────────┐
            │   FastAPI app  (one process)        │
            │                                     │
   client ──┤   api/  → routers per module        │
            │     │                               │
            │     ▼                               │
            │   <module>/service.py  ─────────────┼──→  audit/  ──→ signed log
            │     │                  ─────────────┼──→  dlm/    ──→ Claude API
            │     ▼                  ─────────────┼──→  cashctrl/ ─→ booking spine
            │   <module>/repository.py → Postgres │
            └─────────────────────────────────────┘
                          │
                    Celery + Redis (async AI jobs)
```

Capability modules:

| Module           | What it owns                                                   |
|------------------|----------------------------------------------------------------|
| `identity`       | Tenants (schools), users, roles, permissions, JWT              |
| `accounting`     | GL entries, booking proposals, CashCtrl sync                   |
| `admin`          | Students, parents, staff, org structure                        |
| `scheduling`     | Class schedules, substitute teacher matching                   |
| `contracts`      | Contract templates, e-signing (Swiss standard), versioning     |
| `expenses`       | Submission, approval, reimbursement                            |
| `taxes`          | Swiss source tax, AHV/IV, payroll tax, year-end forms          |
| `signup`         | Student enrollment flow (school applications)                  |
| `addresses`      | Swiss postal validation, geocoding                             |
| `billing`        | Family-based billing, sibling discounts, multi-stage invoicing |
| `documents`      | Ingestion, OCR, classification — the AI surface                |
| `audit`          | Signed audit trail (spine; every module writes here)           |
| `dlm`            | Deterministic Language Model inference + Claude API            |
| `cashctrl`       | Adapter to CashCtrl's REST API (existing bookkeeping spine)    |

## Quick start

```bash
# Prereqs: Python 3.12, uv (or pip), Docker, PostgreSQL
git clone https://gitlab.com/Giansn/entrosana-ai.git
cd entrosana-ai

# Install deps
uv sync                       # or: pip install -e ".[dev]"

# Bring up local Postgres + Redis
docker compose -f docker/dev-stack.yml up -d

# Configure env
cp .env.example .env          # fill in the secrets

# Migrate
alembic upgrade head

# Run API
uvicorn app.main:app --reload

# OpenAPI docs: http://localhost:8000/docs
```

## Status

Phase 0 — architectural skeleton.  Module folders exist with stubs; first
real implementation targets:

1. `identity` (auth + tenant isolation)
2. `audit` (the spine — must be there before any other module writes)
3. `documents` (ingestion + OCR + classification)
4. `accounting` (booking proposals via CashCtrl)

## Licence

AGPL-3.0 where applicable.  See [LICENSE](LICENSE).
