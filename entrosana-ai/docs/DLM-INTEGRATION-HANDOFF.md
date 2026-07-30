# Handoff — wiring the DLM into the capability modules

**Goal:** deliver the product's core promise inside the API — *natural-language
intent → executed action (query or mutation) → signed DB audit row → response* —
so the DLM stops being an isolated POC and drives the real modules + CashCtrl.

**Status today:** the pieces exist but are **not connected**. This is the #1 gap
between "impressive demo" and "usable MVP". Everything below is grounded in the
current code (post-security-remediation, commit `45cee0a`).

---

## What already exists (reuse, don't rebuild)

| Piece | Where | State |
|---|---|---|
| Prose → tool call | `DLMGateway.route_intent(text) -> RoutedIntent(canonical, tool, args)` (`app/dlm/gateway.py`) | ✅ works; `MockRouter` (regex, offline) + `ClaudeRouter` (real, needs `ANTHROPIC_API_KEY` + `intent_route` prompt bundle) |
| Normalization + intent hash | `app/dlm/normalize.py` → `routed.canonical.{normalized,intent_hash,raw}` | ✅ (⚠ see M6 below) |
| DB audit (tamper-evident) | `app.audit.service.record(db, *, tenant_id, actor_id, action, target_type, target_id, before?, after?)` | ✅ hardened (seq + anchored head + rotation) |
| Per-LLM-call log table | `AuditEvent`… `DLMInteraction` (`app/audit/models.py`) | ⚠ table exists, **never written** (audit M4) |
| Real CashCtrl client | `app/cashctrl/client.py` `CashCtrlClient` | ⚠ only `list_journals` / `create_journal` — must grow to the tool repertoire |
| Offline CashCtrl | `app/cashctrl/fake.py` `FakeCashCtrl` | ✅ use for tests |
| Working end-to-end loop (reference) | `app/dlm/demo_intent.py` | ✅ but file-based chain + `FakeCashCtrl`, no endpoint/DB/auth — **pattern to port, not code to ship** |
| Module services (execute + audit) | e.g. `app/billing/service.py:issue_invoice(...)`, one per module | ✅ CRUD-thin; these are the mutation executors |
| Tenant/actor identity | `get_tenant_id` / `get_actor_id` / `get_current_principal` (`app/core/dependencies.py`) | ✅ from verified JWT |

**The missing seam:** nothing maps a routed `tool` name (e.g. `cashctrl.journal_list`,
`billing.invoice.issue`) to an executor, and no endpoint runs
route→execute→audit→respond against the DB with the auth'd tenant.

---

## Target architecture — three new parts

### 1. Tool registry (`app/dlm/tools.py` — new)
A single, explicit map from `tool` name → executor + **arg schema**. The LLM only
*proposes* a tool + args; the registry is the grammar cage — **validate args
against the schema before executing** (never call an executor on raw LLM output).

```python
@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: Literal["query", "mutation"]     # queries read, mutations write
    args_model: type[BaseModel]            # pydantic schema the args MUST validate against
    execute: Callable[..., Awaitable[Any]] # (db, principal, args) -> result

REGISTRY: dict[str, ToolSpec] = {
    "cashctrl.journal_list":  ToolSpec(..., "query",    JournalListArgs,  _cashctrl_journal_list),
    "cashctrl.contact_lookup":ToolSpec(..., "query",    ContactArgs,      _cashctrl_contact_lookup),
    "billing.invoice.issue":  ToolSpec(..., "mutation", InvoiceIssueArgs, _billing_issue_invoice),
    # …one per intent the router can emit; mutations map to module services.
}
```
- **query** executors call `CashCtrlClient` (or a read repository) — source of fact is CashCtrl/DB, never the LLM.
- **mutation** executors call the existing module service (which already does `audit.record`).
- An LLM-proposed tool **not** in the registry → reject (no execution).

### 2. Dispatcher (`app/dlm/dispatch.py` — new)
Ports the `demo_intent.py` loop onto the DB + auth + registry:
```python
async def dispatch(db, principal, user_input) -> AssistantResult:
    routed = await gateway.route_intent(user_input)          # normalize + route
    spec = REGISTRY.get(routed.tool)                          # grammar cage
    if spec is None: raise UnknownToolError(routed.tool)
    args = spec.args_model.model_validate(routed.args)        # validate BEFORE execute
    result = await spec.execute(db, principal, args)          # deterministic execution
    # query path: write ONE query.executed audit row (build_query_audit shape) + a
    #   DLMInteraction row (model/prompt/temperature/in/out) — fixes M4.
    # mutation path: the module service already called audit.record; ALSO write the
    #   DLMInteraction row and link audit_event_id.
    return AssistantResult(tool=routed.tool, args=args, result=result,
                           intent_hash=routed.canonical.intent_hash)
```
Use `audit.record(...)` (DB), **not** the POC's `append_audit` JSONL. Pass
`tenant_id=principal.tenant_id`, `actor_id=str(principal.user_id)`.

### 3. Endpoint (`app/assistant/router.py` — new, mounted like other routers, gated)
```
POST /api/v1/assistant/query    {"input": "pull May payments of Anna Müller"}
```
- Gated by `get_current_principal` (already the app default).
- **Queries execute immediately.** **Mutations must NOT auto-apply** — return a
  *preview* (the routed tool + validated args + a human summary) and require a
  second confirmed call (`POST /assistant/confirm` with the `intent_hash`) before
  the module service runs. This is the safe "propose → verify → apply" the DLM
  base (`Agent.propose`/`Decision`/`audit_chain`) is built for; wire it for writes.

---

## Prerequisite fixes (do these first — they corrupt correctness otherwise)
- **M6 (normalize date-drop):** `app/dlm/normalize.py` silently drops explicit
  numeric date ranges, so the signed `tool_call.args` omits the user's scope. Fix
  + add a golden asserting an ISO/numeric range survives into `args` before wiring
  queries, or every scoped query runs unscoped.
- **M4 (DLMInteraction never written):** implement `record_dlm(...)` and call it
  from the dispatcher (inside the gateway chokepoint) so every LLM call gets a
  pinned, signed row linked to its audit event.
- **Arg validation:** the registry's `args_model.model_validate` is load-bearing —
  it is the only thing standing between an LLM hallucinating a tool arg and a real
  CashCtrl/DB call. Do not skip it.

---

## Phased plan (ship value early, keep risk low)
1. **Read-only assistant (1–2 days).** Registry with the 3 `cashctrl.*` query tools;
   dispatcher; `POST /assistant/query` (MockRouter default). Expand `CashCtrlClient`
   to cover `journal_get` + `contact_lookup`. Golden tests: prose → tool → FakeCashCtrl
   → one `query.executed` DB audit row + one DLMInteraction row. **No mutations yet.**
2. **Claude router live.** Flip to `DLMGateway.for_claude()` behind
   `ANTHROPIC_API_KEY`; ship the `intent_route` prompt bundle; add golden intents.
3. **Mutations behind confirmation.** Add 1–2 mutation tools (e.g.
   `billing.invoice.issue`) mapping to the existing services; preview → confirm flow;
   the service's `audit.record` + a linked DLMInteraction row.
4. **Grow the repertoire + CashCtrl coverage** module by module (expenses, taxes…),
   each as `query`/`mutation` tools with schemas + goldens.

---

## Testing
- **Golden intents** (extend `tests/golden/`): fixed prose → exact `(tool, args)` →
  deterministic execution against `FakeCashCtrl` → assert the DB audit chain (use the
  now-real `audit.verify_chain`) and the DLMInteraction row.
- **Cage tests:** unknown tool → rejected; malformed args → 422, no execution.
- **Mutation safety:** a mutation intent returns a preview and does NOT write until confirmed.
- Reuse `client`/`db` fixtures + the auth helpers in `tests/test_auth.py`.

## Files
- New: `app/dlm/tools.py`, `app/dlm/dispatch.py`, `app/assistant/{__init__,router,schemas}.py`, `tests/test_assistant.py`
- Touch: `app/main.py` (mount assistant router), `app/cashctrl/client.py` (add methods), `app/dlm/normalize.py` (M6), `app/audit/service.py` or a new `record_dlm` (M4), `migrations/` (new revision if `DLMInteraction` columns change).

## Doctrine guardrails (don't violate)
- All LLM access stays behind `DLMGateway` (temperature 0, pinned model/prompt) — no direct `anthropic` calls elsewhere.
- The LLM proposes; execution is deterministic and validated; **CashCtrl/DB is the source of fact — the LLM never invents data.**
- Every executed intent (query or mutation) produces a signed DB audit row; mutations additionally require explicit user confirmation.
