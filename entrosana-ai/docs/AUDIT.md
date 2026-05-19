# Audit report — 2026-05-19

Single-pass audit of the entrosana-ai codebase prior to consolidation of
`arboro/dlm/` (standalone) and `proposal/compact-dlm-base` (branch) into
`main`.  Goal: every line in the repo has been read, every claim in the
README verified, every cryptographic primitive tested end-to-end, and every
issue fixed in-place or flagged here with severity.

## Scope

| area | depth |
|---|---|
| `app/dlm/base/` (transducer, signer, audit primitives) | full read, modified to add `Provenance`, regression tests |
| `app/audit/` (recording service + models + router) | full read, **critical bug found + fixed**, 16 tests added |
| `app/dlm/` (runner, intent, demo, prompts) | full read, mypy fix |
| `app/cashctrl/` (client + fake backend) | full read |
| `app/core/` (config, database, dependencies, logging, tracing) | full read |
| `app/main.py` (FastAPI wiring) | full read |
| 11 capability modules (accounting … taxes) | sampled accounting in full; verified all 11 are structurally identical scaffolds |
| `app/tasks/` (Celery placeholders) | full read |
| `migrations/` | listed |
| `Dockerfile`, `docker/dev-stack.yml` | full read |
| `tests/` | full read |
| `pyproject.toml`, `.env.example`, `.gitignore` | full read |
| `README.md`, `docs/ARCHITECTURE.md`, `docs/POC.md` | full read |
| `arboro/dlm/` (now folded in) | full read |

Total LOC reviewed: ~3,400.

## Findings — fixed this session

### CRITICAL — audit chain could never verify itself

**Where**: [`app/audit/service.py:record()`](../app/audit/service.py) and
[`app/audit/models.py:AuditEvent.created_at`](../app/audit/models.py).

**Bug**: `record()` signed `datetime.utcnow().isoformat()` at one instant
and stored an `AuditEvent` whose `created_at` was filled by SQLAlchemy's
column default — a separate `datetime.utcnow()` call microseconds later.
The two timestamps differed in the microsecond field.  `verify_chain()`
recomputed the signature using `e.created_at.isoformat()` (the *stored*
time, not the *signed* time), so every audit row failed verification.

The brand promise — "audit-grade" — could not be honoured by the code.

**Reproduction** (run in any audit-service-aware shell):

```
  signed_ts:      2026-05-19T17:57:47.812317
  stored ts:      2026-05-19T17:57:47.813949
  signing sig:    0ea27fda7a0b472430a537e6…
  verifying sig:  e0433274bf5737f2fe90ed14…
  match: False
```

**Fix**:

1. Compute `ts = datetime.now(UTC).replace(tzinfo=None)` **once** in
   `record()`.
2. Pass that `ts` to `_build_payload(ts_iso=ts.isoformat())` *and* to
   `AuditEvent(..., created_at=ts)` — same instant, same bytes.
3. Extracted `_build_payload()` so signing and verification share one
   payload builder — drift between the two paths is no longer possible.
4. Naive UTC chosen over tz-aware: SQLite drops tzinfo on read and would
   silently re-break verification in any future SQLite-backed test.
5. Added 7 end-to-end regression tests
   ([`tests/test_audit_chain.py`](../tests/test_audit_chain.py)) covering
   record→verify roundtrip, tenant isolation, payload-tamper detection,
   hmac-tamper detection, GENESIS persistence, empty-chain handling, and
   timestamp consistency.

### Medium — `datetime.utcnow()` deprecated

Python 3.12 deprecated `datetime.utcnow()` in favour of
`datetime.now(UTC)`.  Three call sites updated:
[`app/audit/service.py`](../app/audit/service.py),
[`app/audit/models.py`](../app/audit/models.py), and the canonical
`arboro/dlm/` package (via the audit pass).

### Medium — `app/dlm/runner.py` mypy union errors

11 mypy errors from `resp.content[0].text` — the anthropic SDK returns a
union of content-block types and only `TextBlock` exposes `.text`.  Fixed
with an explicit type guard:

```python
for block in resp.content:
    if isinstance(block, anthropic.types.TextBlock):
        output_text = block.text
        break
```

### Low — legacy lint and format

Pre-existing: 66 ruff errors (mostly I001 import-order) and 77 unformatted
files.  Auto-fixed in one mechanical pass (`ruff check --fix && ruff
format`).  Settings updated to ignore three rules that are false-positives
in this codebase: `B008` (FastAPI `Depends(...)` argument defaults),
`UP042` (compact `class X(str, Enum)` style used in the DLM core),
`S603/S607` (subprocess with literal `git` argv in `env_fingerprint.py`).

## Findings — flagged, not fixed

### Medium — tenant isolation rests on an unverified header

[`app/core/dependencies.py:get_tenant_id()`](../app/core/dependencies.py)
reads `X-Tenant-Id` from the request header.  Anyone hitting the API can
claim any tenant id.  The docstring already labels this a stub.

**To fix**: replace the header read with a JWT-derived claim once
`app/identity/` actually issues tokens.  Until then, the FastAPI service
should not be exposed to untrusted networks.

### Medium — actor attribution is forged

Every router POST endpoint hardcodes `actor_id="system"`.  Audit rows
attribute every mutation to "system" rather than the real user.

**To fix**: same JWT story as above.  Until tokens carry user identity,
audit attribution is decorative.

### Medium — empty migrations directory

[`migrations/versions/`](../migrations/) contains no migration files.  The
schema lives only in `models.py`.  Production deployments cannot evolve
the schema without first generating the initial migration:

```bash
alembic revision --autogenerate -m "initial schema"
```

This requires a running Postgres to compare against.  Out of scope for
the offline audit; flagged for the next environment-touching session.

### Medium — capability modules are uniform scaffolds, not implementations

All 11 modules (`accounting`, `admin`, `billing`, `contracts`,
`documents`, `expenses`, `identity`, `scheduling`, `signup`, `taxes`,
`addresses`) share an identical 5-file structure differing only in the
class name and table name.  Their `service.py` files contain a single
`create_*` method that calls `audit.record()` — the audit-write pattern
is faithful, but there is no real domain logic anywhere.

This is **accurately** reflected in the README's "Status" section as
"capability service layers are scaffolds".  No deception; flagged as
material context for any technical buyer.

### Medium — `app/dlm/prompts/v0.1.0/` has one prompt

[`intent_route.md`](../app/dlm/prompts/v0.1.0/intent_route.md) is the
only prompt bundle.  The README implies a wider library (`booking_propose`,
`document_classify`, `contract_summarise` in
`app/dlm/README.md`).  Those names do not yet exist on disk.

**To fix**: either add the other bundles or trim the README's example list.

### Low — CORS permissive

`app.main:app` mounts `CORSMiddleware` with `allow_methods=["*"]` and
`allow_headers=["*"]`.  Restrict to the explicit list once auth is wired
(at minimum: `["GET", "POST", "PUT", "PATCH", "DELETE"]`, headers
`["Authorization", "Content-Type", "X-Tenant-Id"]`).

### Low — no rate limiting

No middleware enforces request-rate caps.  For a public API serving
financial data, add `slowapi` or equivalent.

### Low — Pydantic schemas have no field validation

Every `schemas.py` has plain `name: str`.  No `min_length`, `max_length`,
or pattern constraints.  Acceptable while the modules are scaffolds;
must be hardened before any real client uses the API.

### Low — Dockerfile could use a multi-stage build

`apt-get install build-essential libpq-dev` stays in the runtime image.
A two-stage build would shrink production image and reduce attack
surface.  Non-root user (`entrosana` UID 1000) and `HEALTHCHECK` are
already present — those are the high-leverage items.

### Low — passlib is in dependencies but never imported

`passlib[bcrypt]` is in `[project.dependencies]` of `pyproject.toml`.
No file imports it.  Either implement password hashing in
`app/identity/` or remove the dep until needed.

### Low — `app/tasks/` are documented stubs

[`document_ocr.py`](../app/tasks/document_ocr.py) and
[`payroll_calc.py`](../app/tasks/payroll_calc.py) both return
`{"status": "queued"}` without doing work.  Docstrings label them as
stubs — honest, but flagged as a real implementation gap.

## Findings — none found

These were searched for and not present:

- `eval(`, `exec(`, `pickle.loads(`, `os.system(`, `yaml.load(` without `Loader=` — **none**
- Raw SQL string concatenation — **none** (every query goes through SQLAlchemy ORM)
- Tenant-leak bugs in repository layer — **none** (every `select` filters by `tenant_id`)
- Missing audit calls on mutation paths — **none** (every `service.py:create_*` calls `audit.record()`)
- Hardcoded secrets — **none** (test-only values are clearly labelled, real config reads `os.environ`)
- TODO / FIXME / XXX / HACK markers in app + tests + scripts — **none**

## Verification — what passes now

```
pytest:               17/17  pass
ruff check:           clean  on app/ + tests/ + scripts/
ruff format --check:  clean  on 101 files
mypy:                 clean  on 95 source files (--no-strict-optional)

example_school.py:    PASS signature  PASS content  PASS replay
demo_intent.py:       two roundtrips → audit-demo.jsonl, chain verified by independent script
verify_audit_chain.py: PASS clean log;  FAIL on tampered row (exit 1)

GitLab CI pipeline (post-fix):
  lint:ruff            success  (20s)
  test:unit            success  (56s)  ← 17 tests, postgres + redis services
  build:docker         success  (115s) ← image built, pushed to registry
```

## Post-merge CI gap and corrections

The first audit pass declared sign-off on local tests + lint + mypy but
**did not run CI**.  Inspecting GitLab afterward revealed that every CI
run since the audit branch had failed.  Two environment-drift bugs:

### test:unit — `ModuleNotFoundError: aiosqlite`

`uv add --dev aiosqlite` (used during the audit pass) writes to
`[dependency-groups].dev` in `pyproject.toml` — the uv-specific section.
CI's `pip install -e ".[dev]"` reads only `[project.optional-dependencies].dev`,
so aiosqlite was never installed in CI.  Locally `uv sync --extra dev`
satisfies both sections, so the gap was invisible.

**Fix** (`3839ccb`): moved aiosqlite into `[project.optional-dependencies].dev`
and dropped the now-empty `[dependency-groups]` block.

### build:docker — hatchling can't find `app/` (pre-existing)

The Dockerfile did `COPY pyproject.toml ./` → `RUN pip install -e .`
*before* copying `app/`.  Hatchling resolves
`[tool.hatch.build.targets.wheel] packages = ["app"]` at install time
and fails when the directory is absent.  Every prior `build:docker`
job had been failing for this reason — pre-existing breakage the
initial audit didn't catch.

**Fix** (`b82c83e`): copy `app/` (and `README.md`, referenced by
`readme = "README.md"` in pyproject) before the install.

### Lesson recorded

For future audit passes: **run CI**, not just local tests.  The two
failures above were structural — neither would have been visible to any
amount of local-only verification.

## What changed in the repo this session

```
A  docs/AUDIT.md                   (this file)
A  docs/POC.md                     (end-to-end walkthrough)
A  app/dlm/intent.py               (MockRouter + ClaudeRouter)
A  app/dlm/demo_intent.py          (POC CLI)
A  app/cashctrl/fake.py            (deterministic in-memory backend)
A  app/dlm/prompts/v0.1.0/intent_route.md  (first pinned prompt bundle)
A  scripts/verify_audit_chain.py   (independent chain verifier)
A  uv.lock                         (dependency lock)

M  README.md                       (Provenance pivot, Input provenance section, POC link, Status update)
M  app/audit/service.py            (timestamp-consistency fix + shared _build_payload)
M  app/audit/models.py             (naive UTC + helper _utcnow_naive)
M  app/dlm/runner.py               (mypy fix: TextBlock isinstance guard)
M  app/dlm/base/core.py            (Provenance enum + Features/Decision fields + _signing_payload)
M  app/dlm/base/__init__.py        (exports Provenance)
M  app/dlm/base/verify_replay.py   (reads Provenance from Decision JSON)
M  tests/conftest.py               (env-var defaults so app.* imports work in tests)
M  tests/test_audit_chain.py       (was a 4-line stub → 16 cryptographic + roundtrip tests)
M  pyproject.toml                  (ignore B008/UP042/S603/S607 false positives)
M  .gitignore                      (ignore audit*.jsonl runtime artifacts)
M  77 legacy files                 (auto-formatted)

D  scripts/vendor-dlm.py           (consolidated — entrosana-ai is the single source of truth)

Plus: arboro/dlm/.git removed (un-gitted; files preserved as a workbench)

Follow-up commits after CI inspection:
  3839ccb fix(ci): aiosqlite in [project.optional-dependencies].dev
  b82c83e fix(docker): copy app/ before pip install -e .
```

## Sign-off

The audit-grade core — signed audit chain with tamper detection,
deterministic DLM transducer with replay theorem, provenance tagging
on every Decision and Feature — is verified end-to-end through 16
automated tests, one runnable POC, and a green GitLab CI pipeline
(lint + test + Docker build all passing).

The application layer above that core is honestly described in the
README as scaffold-stage.  Anyone evaluating the repo can run
`uv sync --extra dev && python -m app.dlm.base.example_school` and
`python -m app.dlm.demo_intent "..."` to see the audit-grade claim hold
under tamper.
