# ADR 0002 — Declarative accounting-provider specs (adapters as data)

- **Status:** Accepted — implemented on `feat/declarative-provider-specs`
- **Date:** 2026-07-23
- **Supersedes:** the code-adapter sketch in `docs/DLM-INTEGRATION-HANDOFF.md`
  (the tool registry is now spec-driven and provider-agnostic).

## Context

The DLM was wired to CashCtrl specifically: the intent router emitted `cashctrl.*`
tool names and a hand-written `CashCtrlClient` executed them. Entrosana's users
(Swiss schools/agencies) are fragmented across CashCtrl, bexio, Abacus, Banana,
Sage/Topal and others, so the product has to run against **any** accounting
backend — without forking the deterministic/audit core per vendor, and while
staying drivable by a **small offline model** (the local Granite-class router),
not just a frontier LLM.

Writing one Python adapter class per vendor does not meet this: it couples backend
knowledge into code, multiplies the surface a small model would have to reason
about, and makes each new provider a code change rather than a data change.

## Decision

**Adapters are data, not code.** One deterministic executor runs every provider
from a pinned declarative spec. Concretely, the `app/providers/` package:

| Layer | File | Responsibility |
|---|---|---|
| Canonical vocabulary | `vocabulary.py` | The only ops the router may emit (`contact.lookup`, `journal.list`, `journal.get`, `journal.create`) + their pydantic **arg models**. Provider-neutral. Grammar cage. |
| Spec schema | `spec.py` | Declarative `ProviderSpec` → per-op HTTP binding (method, path template, param map, response map) or composite `steps` (sequential, `when_arg`-conditional, `prev`-chained). YAML loader. |
| Executor | `executor.py` | **One** engine: build request → send → map response to canonical, incl. `steps` execution. No clock, no randomness. Fails loud (see Hardening). |
| Transport | `transport.py` / `fake.py` | `HttpxTransport` (real) vs `FakeCashCtrlTransport` (offline fixtures). Executor is transport-agnostic. |
| Registry | `registry.py` | Load specs; resolve `tenant → provider`; build an executor. |
| Path-finder | `pathfinder.py` | **Author-time** OpenAPI → proposed bindings (offline, advisory). |
| Specs | `specs/*.yaml` | Each provider. `cashctrl.yaml` is the reference. |

The tools are renamed from vendor-specific `cashctrl.*` to operation-based
canonical ops. The dispatcher (`app/dlm/dispatch.py`) and endpoint
(`POST /api/v1/assistant/query`) run the provider-agnostic path.

### The load-bearing split: author-time vs runtime

- **Author-time (occasional, reviewed):** discover which endpoint implements each
  canonical op (`pathfinder.py` assists from an OpenAPI doc), then **hard-code** it
  into a pinned, versioned `specs/<name>.yaml`, gated by contract tests. All the
  guessing happens here, under human review.
- **Runtime (deterministic, offline):** a small model only does prose → canonical
  op + args, grammar-caged (fixed op enum + `extra="forbid"` arg models). Everything
  after that is mechanical: the executor fills the pinned spec and calls. No API
  reasoning at runtime.

This is why a 2–8B local model can drive it: its job is a short classification +
schema fill, not understanding an API.

### Determinism & audit

The executor is pure (no time/randomness), so `(spec_version, op, args)` reproduces
a result exactly. The audit chain records the canonical op + provider name + spec
version + result count; a signed `DLMInteraction` row pins the routing. The doctrine
holds unchanged: **the LLM proposes; execution is deterministic and validated; the
provider/DB is the source of fact.**

### Capability negotiation

A provider implements an op iff a binding is present (`spec.capabilities`). A valid
op the tenant's provider lacks returns `UnsupportedOperationError` → HTTP 501, not a
crash — so a file-based backend that can't post live entries degrades honestly.

## Adding a provider (the whole checklist)

1. `python -m app.providers.pathfinder <vendor-openapi.json>` → draft bindings.
2. Complete `app/providers/specs/<vendor>.yaml` (query/response mappings, auth by
   settings reference — **never inline secrets**). Verify field names vs the live API.
3. Point a tenant at it via `accounting_provider_bindings` (or `default_...`).
4. Make it pass the same contract-test shape as `tests/test_providers.py`.

No executor, dispatcher, vocabulary, or endpoint change. That is the win.

## Consequences

**Positive:** new backend = a reviewed YAML + green contract tests, not code; the
deterministic/audit core is written once; the moat (audit-grade AI) sits above a
swappable backend, widening TAM beyond CashCtrl shops; small-offline-model drivable.

**Negative / accepted cost:** the canonical model is the real design work and grows
as ops are added; per-vendor field mappings need verification against the live API
(path-finding is advisory, never trusted blind); the arg cage is load-bearing (a
small model *will* hallucinate — validation between model output and executor is the
only guard).

## Hardening (adversarial review round 1 — 10 confirmed findings, all fixed)

A 6-dimension adversarial review (determinism, cage/injection, audit, security,
correctness, doctrine) with per-finding verification confirmed 10 defects; every
fix is regression-tested (`tests/test_providers.py`, `tests/test_assistant.py`):

- **Composite `steps` executed** (was deferred): `when_arg`-conditional resolution
  steps, `prev`-chained params with `fallback_arg`; a fired resolve step that finds
  nothing **short-circuits to an empty result** — a scoped query can never silently
  run unscoped. CashCtrl `journal.list` by contact name is now a real 2-step op.
- **Unconsumed-arg guard:** a provided filter the binding can't send ⇒ refuse, not
  silently widen the query.
- **HTTP-200 error envelopes** (`success_path`/`error_message_path`): a logical
  provider failure raises instead of being signed as an empty success.
- **Pagination honesty:** exceeding `_MAX_PAGES` or a non-advancing cursor raises —
  a truncated/duplicated list is never signed as authoritative. `next_cursor_path`
  and `cursor_param` must be declared together.
- **Per-tenant credentials** (`accounting_tenant_credentials` + executor
  `credential_overrides`): multi-tenant production must not share one provider
  account — a single global key means one shared data pool.
- **Secrets fail closed:** an unset credential refuses the request; no blank bearer.
- **Two-phase signed queries:** `query.requested` is committed *before* the provider
  is called, `query.executed` + the DLMInteraction row after — an executed read can
  never end up with zero committed audit trail (dispatcher owns commits now).
- **Mutation previews are signed provenance:** `mutation.proposed` + DLMInteraction
  row; an LLM-proposed financial write is traceable even if never confirmed. The
  preview path also resolves + capability-checks the provider (fails as loudly as
  a read on misconfiguration).
- **Spec version pinned in the signed rows** (`spec_version` in audit `after` +
  `CanonicalResult`), honoring the replay claim.

## Hardening (external audit round 2 — Grok, 9 findings, all fixed)

An independent external audit (Grok, read-only, adversarially re-breaking round 1)
confirmed the round-1 rails hold and found 9 further defects; verdict was
SHIP-WITH-FIXES and every finding is fixed + regression-tested:

- **Prompt bundle v0.2.0:** the pinned `intent_route` prompt taught the retired
  `cashctrl.*` names — every real-LLM call would have died in the cage while the
  Mock-based suite stayed green. New pinned version teaches only canonical ops
  (incl. `journal.create`); `dlm_prompt_version` bumped. A test asserts the active
  prompt names every canonical op and no vendor op.
- **Path args percent-encoded** (`quote(..., safe="")`): an LLM-proposed
  `../admin`, `x?evil=1`, or CRLF-bearing path arg cannot escape its segment.
- **Whitespace-only secrets refused** (strip before the fail-closed check).
- **Contradictory contact scope refused:** `journal.list` with both `contact_id`
  and `contact_name` fails validation instead of silently preferring the name.
- **Base URL fails closed:** unset/non-http(s) base refuses the call — also stops
  a mis-pointed `base_url_setting` from leaking an arbitrary settings value.
  Per-tenant overrides may carry the base URL too (per-org subdomains).
- **`MoneyStr` cage:** amounts are strict decimal strings (`""`, `1e10`,
  padded, comma, >2 fraction digits all rejected before a signed proposal).
- **Envelope boolean-strict:** the string `"false"` no longer passes a truthiness
  check; only `True`/`1`/`"true"` count as success.
- **Malformed list payloads fail loud:** a non-array payload or non-object list
  element raises instead of signing an under-count as complete.
- **Production guard:** every tenant in `accounting_provider_bindings` must have
  `accounting_tenant_credentials` in production, enforced at startup.

## Deferred (explicit, not silently missing)

- **OAuth2 auth** (bexio/Xero/QuickBooks): `AuthKind.OAUTH2` is declared; execution
  is not wired (bearer/api-key/basic are).
- **DB-backed per-tenant bindings + encrypted credential storage:** today both are
  settings-backed; a binding/credential table drops in behind
  `registry.provider_for_tenant` / `credentials_for_tenant` without touching
  anything else.
- **Mutation confirm leg:** mutations return a signed preview (`executed: false`);
  the `POST /assistant/confirm` that actually writes is the next increment.
