# entrosana-ai

> Audit-grade AI for back-office work.  Swiss-hosted, deterministic, built on CashCtrl.

This is the API monolith powering [entrosana.com](https://entrosana.com).
A FastAPI app organized into capability modules (accounting, admin, scheduling,
contracts, expenses, taxes, signup, addresses, billing, documents) that all
write through a single signed audit trail.

**Try it yourself** → [Proof of concept](#proof-of-concept) (runnable demo, no DB / no API key) · [`docs/POC.md`](docs/POC.md) (full walkthrough) · [`docs/AUDIT.md`](docs/AUDIT.md) (codebase audit report)

## Why deterministic

A regular LLM is creative.  For back-office work — bookkeeping, payroll, contracts
— consistency and auditability matter more than novelty.

**Inputs to the audited decision come from a system of record, not from an LLM.**
The LLM's job is to translate a user's natural-language intent into a concrete
API call against CashCtrl, then format the response back:

> "Pull the May payments of Anna Müller" →
> `GET cashctrl://journal/list?contact=4827&from=2026-05-01&to=2026-05-31`

CashCtrl's response is the canonical truth.  The agent reasons over those exact
rows; it never reasons over an LLM's parsing of a free-text document.  Document
understanding, OCR, and free-text extraction are not in the audit-grade path —
see [Input provenance](#input-provenance).

The **audit-grade decision path** is a deterministic transducer over a versioned
`(Lexicon, Grammar)` — see [`app/dlm/base/core.py`](app/dlm/base/core.py).  Same
canonical inputs + same artifacts → same output bytes, forever.  Replay is a
theorem, not a hope.

The **LLM wrapper** in [`app/dlm/runner.py`](app/dlm/runner.py) is the single
chokepoint for any LLM call.  It routes intent and formats results; it is not
allowed to invent values that touch the audit chain.  Direct
`anthropic.Anthropic()` calls anywhere else in the codebase are forbidden.
Every call:

- `temperature 0`
- pinned model version (no `claude-sonnet-latest`)
- pinned prompt version (versioned bundle on disk)
- deterministic retrieval order (stable sort keys)
- signed audit row per call (`audit.dlm_interactions`)

## Architecture

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).  TL;DR:

```
            ┌─────────────────────────────────────┐
            │   FastAPI app  (one process)        │
            │                                     │
   client ──┤   api/  → routers per module        │
            │     │                               │
            │     ▼                               │
            │   <module>/service.py  ─────────────┼──→  audit/     ──→ HMAC-chained log
            │     │                  ─────────────┼──→  dlm/       ──→ intent router (Claude)
            │     ▼                  ─────────────┼──→  cashctrl/  ──→ system of record
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
| `documents`      | Inbound document handling — QR-invoice import, OCR preview, vendor-portal sync |
| `audit`          | Signed audit trail (spine; every module writes here)           |
| `dlm`            | Deterministic transducer (`base/`) + intent-routing LLM wrapper (`runner.py`) |
| `cashctrl`       | Adapter to CashCtrl's REST API (existing bookkeeping spine)    |

## Input provenance

Three classes of input, three audit treatments:

- **System of record (CashCtrl)** — primary source.  GL entries, contacts,
  documents already filed.  Always re-fetched per query; never cached for
  decisions.  Audit row records the query and timestamp.  **Deterministic.**
- **User-typed** — direct entry from the school's accountant or owner
  (e.g. an amount on a manual booking).  Recorded verbatim in the audit row,
  attributed to `actor_id`.  **Deterministic.**
- **Third-party providers** (banks, Swissdec, postal address, etc.) — fetched
  via API.  Recorded with `source: provider:<name>` and
  `non_deterministic: true` in the audit row.  The agent may use these values,
  but the Decision carries provenance forward so a revisor sees which fields
  are attested by entrosana vs. by an outside system.

OCR'd or LLM-parsed values from free-text documents are **not** in this list.
If a document carries data that must enter the audit chain, the data lands in
CashCtrl first (e.g. via Swiss QR-invoice import, vendor portal, or accountant
review) and then becomes a system-of-record input on the next query.

### Session memory

The LLM holds 24-hour session context to connect follow-up queries
("now do June" after "pull May payments of Anna Müller").  Session memory
stores intent only — never decision data.  Every actionable query re-fetches
from CashCtrl so the data shown is always fresh and its audit row reflects a
real fetch.

## Audit-grade in practice

The audit trail is a hash-chained, HMAC-signed append-only log
([`app/audit/service.py`](app/audit/service.py)):

- Each event signs `HMAC(prev_event.hmac ‖ canonical(payload))`
- The first event of any tenant chains to the literal string `"GENESIS"`
- Editing any historical event breaks every subsequent HMAC

Third-party reproducibility — a revisor (or the school's accountant)
re-derives any stored Decision and checks its signature against the source:

```bash
python -m app.dlm.base.verify_replay \
    --decision  decisions/inv-001.json \
    --features  features/inv-001.json \
    --key-id    2026-q2 \
    --dlm-module app.dlm.base.example_school
# exit 0 ⇔ every check passes
```

What the verifier confirms: the stored Decision is reproducible from its inputs
under the current DLM, the HMAC validates against the named key, and the
alternatives + confidence are consistent with the rules.

The runtime environment that produced a Decision is captured by
[`app/dlm/base/env_fingerprint.py`](app/dlm/base/env_fingerprint.py):
Python version, platform, git SHA + dirty flag, and SHA-256 of the source
files that contributed.  Decisions are pinned not just to a model + prompt,
but to an exact code revision.

## Proof of concept

Two runnable end-to-end demonstrations of the doctrine — **no DB, no Docker,
no API key** required.  After `uv sync --extra dev`:

The **DLM transducer** end-to-end — a realistic Swiss school, EWZ + Migros
vendors, real chart of accounts:

```bash
python -m app.dlm.base.example_school
# propose · audit · sign · verify, on a fixture invoice
```

The **intent-routing POC** — prose in, signed audit row out:

```bash
python -m app.dlm.demo_intent "pull May payments of Anna Müller"
python -m app.dlm.demo_intent "show me journal JE-2026-0445"
# appends one signed row per run to ./audit-demo.jsonl
# add --use-claude to swap the regex router for Claude (needs ANTHROPIC_API_KEY)
```

The audit chain in `audit-demo.jsonl` is independently verifiable.  Each row's
`prev_hmac` matches the previous row's `hmac`, every `hmac` is reproducible by
recomputing `HMAC(prev ‖ canonical(payload))`, and the first row chains from
the literal `"GENESIS"`.  Run the independent verifier:

```bash
python scripts/verify_audit_chain.py audit-demo.jsonl
```

A complete walkthrough — including tamper detection and reading one audit row
field-by-field — lives in [`docs/POC.md`](docs/POC.md).  For the codebase
audit (every file read, every claim verified, every issue fixed or severity-
rated), see [`docs/AUDIT.md`](docs/AUDIT.md).

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

To verify the doctrine end-to-end without standing up the database, see
[Proof of concept](#proof-of-concept) above.

## Status

Foundations built: DLM transducer with `Provenance` tagging
([`app/dlm/base/core.py`](app/dlm/base/core.py)), HMAC-chained audit service
with tamper-detection tests ([`app/audit/service.py`](app/audit/service.py),
[`tests/test_audit_chain.py`](tests/test_audit_chain.py)), CashCtrl sink,
replay verifier, end-to-end school example, intent-router POC
([`app/dlm/demo_intent.py`](app/dlm/demo_intent.py)) backed by the first
pinned prompt bundle
([`app/dlm/prompts/v0.1.0/intent_route.md`](app/dlm/prompts/v0.1.0/intent_route.md))
and a deterministic in-memory CashCtrl
([`app/cashctrl/fake.py`](app/cashctrl/fake.py)).

Known gaps: capability service layers are scaffolds;
[`app/dlm/runner.py`](app/dlm/runner.py) is a generic LLM caller (the
intent-routing prompt exists but `runner.py` doesn't yet enforce that callers
emit only structured tool calls); the real CashCtrl client
([`app/cashctrl/client.py`](app/cashctrl/client.py)) covers only
`journal_list` and `journal_create` and needs broadening to match the intent
router's tool catalog.

### Next vertical implementations

1. `identity` (auth + tenant isolation)
2. `cashctrl/client.py` broadening — real-API tool catalog matching the
   intent router
3. `accounting` (booking proposals via CashCtrl)
4. `documents` (QR-invoice import, OCR preview path — non-audit)

## Licence

AGPL-3.0 where applicable.  See [LICENSE](LICENSE).
