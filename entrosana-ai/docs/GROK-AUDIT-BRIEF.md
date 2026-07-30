# Audit brief for Grok — declarative accounting-provider layer

**Branch:** `feat/declarative-provider-specs`
**Scope:** the new `app/providers/` subsystem + its DLM/endpoint wiring (ADR 0002).
**Why you:** an independent second pass. A self-adversarial review (6 dimensions,
per-finding verification) ran first and its confirmed findings are already fixed;
you are the external cross-check, not the first net.

## What this subsystem does

Adapters are **data, not code**. The DLM router emits a provider-neutral canonical
op (`contact.lookup` / `journal.list` / `journal.get` / `journal.create`) + args;
args are validated against a pydantic grammar cage; **one** deterministic executor
runs any provider from a pinned YAML spec over a `Transport`; the dispatcher writes
a signed audit row + `DLMInteraction` row; `POST /api/v1/assistant/query` is the
entrypoint. Author-time `pathfinder.py` proposes endpoint bindings from an OpenAPI
doc (advisory, offline); runtime is a small-model-drivable classify-and-fill.

## Files to audit

```
app/providers/{vocabulary,errors,spec,transport,fake,executor,registry,pathfinder}.py
app/providers/specs/cashctrl.yaml
app/dlm/dispatch.py        app/dlm/intent.py (renamed tools)
app/assistant/{router,schemas}.py
app/core/dependencies.py (get_accounting_transport)   app/core/config.py (provider settings)
tests/test_providers.py    tests/test_assistant.py
docs/adr/0002-declarative-provider-specs.md
```

## Invariants to attack (please try to break these)

1. **Determinism / replay:** same `(spec_version, op, args)` ⇒ identical result and
   identical signed audit bytes. Look for clock/randomness/iteration-order leaks.
2. **Grammar cage:** no LLM-proposed value reaches a real HTTP call without passing
   `validate_args`. Try path-template injection (`_fill_path`), param/body injection,
   extra keys, `_dig` traversal abuse. A small model *will* hallucinate — is the cage
   the only gate, and is it airtight?
3. **Audit integrity:** every executed query signed exactly once; mutation preview
   writes nothing; endpoint commits only when `executed`. No partial/committed state
   on error.
4. **Secrets:** never in error messages/logs; auth headers built correctly; no SSRF
   via `base_url_setting`; the fake transport unreachable in prod.
5. **Tenant isolation:** the registry singleton holds no cross-tenant mutable state;
   provider resolution is per-tenant.
6. **Doctrine fit:** all LLM access behind `DLMGateway`; canonical-only tool names
   (no `cashctrl.*` leaks); provider is the source of fact.

## Already fixed in round 1 (self-review) — re-break them if you can

10 confirmed findings were fixed and regression-tested (ADR 0002 §Hardening):
composite `steps` execution with empty-short-circuit (no silently-unscoped
queries), unconsumed-arg guard, HTTP-200 error-envelope checks, pagination
truncation/non-advancing-cursor refusal, per-tenant credentials, fail-closed
secrets, two-phase signed queries (`query.requested` committed pre-execution),
signed mutation proposals (`mutation.proposed` + DLMInteraction), spec version
pinned in the signed rows. Verifying these fixes hold under adversarial input is
in scope.

## Known-deferred — do NOT file these as bugs (see ADR 0002 §Deferred)

- OAuth2 auth (declared `AuthKind.OAUTH2`; not wired).
- DB-backed per-tenant bindings + encrypted credential storage (settings-backed).
- Mutation confirm leg (`/assistant/confirm`) — mutations only preview today.
- CashCtrl wire field names in `cashctrl.yaml` are MODELED for the reference adapter
  + fake; they carry a "verify vs live API" caveat, not a claim of correctness.

## How to run

```
uv run pytest -q            # 73 tests
uv run ruff check app       # clean
uv run mypy app/providers app/assistant app/dlm/dispatch.py   # clean
```

## Where to leave findings

Reply to Gianson with a ranked list (severity, file:line, concrete failure scenario).
Gianluca will relay them to me and I'll triage + fix, then we reconcile.
