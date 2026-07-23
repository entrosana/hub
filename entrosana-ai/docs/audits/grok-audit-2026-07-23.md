I'll start from the audit brief, then walk the declarative provider layer and try to re-break the round-1 fixes with concrete inputs.Confirmed on the right commit. Reading the provider subsystem and wiring next.Found a likely doctrine break: the intent-route prompt still lists `cashctrl.*` tools. Verifying that and other attack paths.Checking one more interaction: whether the dispatch path would surface the Claude prompt break end-to-end.# External audit — declarative accounting-provider layer

**Target:** `feat/declarative-provider-specs` @ `6b0f73a`  
**Mode:** read-only, adversarial re-break of round-1 fixes + invariant attack  
**Scope:** files listed in `docs/GROK-AUDIT-BRIEF.md`

---

## Findings (most severe first)

### 1. HIGH — Claude path teaches vendor ops the cage always rejects

**Where:** `app/dlm/prompts/v0.1.0/intent_route.md:12–40` → consumed by `app/dlm/intent.py:139–151` (`ClaudeRouter` → `intent_route`) → rejected at `app/dlm/dispatch.py:92` (`get_op`)

**Defect:** Pinned prompt still documents and exemplifies `cashctrl.journal_list` / `cashctrl.contact_lookup` / `cashctrl.journal_get`. Canonical vocabulary only accepts `journal.list` / `contact.lookup` / `journal.get` / `journal.create`. Doctrine “no `cashctrl.*` leaks” fails in the only real-LLM instruction surface.

**Concrete failure:**
1. Operator enables Claude: `DLMGateway.for_claude()` / `ClaudeRouter`.
2. Model follows the prompt, returns  
   `{"tool":"cashctrl.journal_list","args":{"contact_name":"Anna Müller","date_from":"2026-05-01","date_to":"2026-05-31"}}`.
3. `get_op("cashctrl.journal_list")` → `UnknownOpError`.
4. Endpoint → **HTTP 422**; no provider call, no useful assistant answer.

Hand-checked: all three legacy tool names fail the cage. MockRouter/golden tests use canonical names, so the suite stays green while the Claude path is dead.

---

### 2. HIGH — Path placeholders are raw-interpolated (traversal / CRLF / query breakout)

**Where:** `app/providers/executor.py:253–261` (`_fill_path`), used at `:172`

**Defect:** `str(val)` is substituted with no encoding, segment restriction, or CRLF rejection. Grammar cage does not constrain free-string path args (e.g. `journal.get`’s `id: str`).

**Concrete failure** (spec with path param — legal under the schema; next provider / any path-templated binding):

| Input `id` | Built URL |
|---|---|
| `../admin/secret` | `https://api.example.com/journal/../admin/secret/read` |
| `x?evil=1` | `.../journal/x?evil=1/read` |
| `x\r\nX-Injected: yes` | path/URL contains raw CRLF |

LLM proposes `journal.get` with that `id` → executor issues a non-intended path against the configured base host.  
**Current `cashctrl.yaml` has no `{arg}` path segments** (ids go in query), so CashCtrl is not exploitable today; the executor API is.

---

### 3. MEDIUM — “Fail-closed secrets” still accepts whitespace-only credentials

**Where:** `app/providers/executor.py:326–337` (`_secret`)

**Defect:** Guard is `if not val:` only. `"   "` is truthy, so blank-looking secrets are sent.

**Concrete failure:**
1. `CASHCTRL_API_KEY="   "` or tenant override `{"cashctrl_api_key": "  "}`.
2. `contact.lookup` with `{"id": 1}`.
3. Request goes out with `Authorization: Bearer    ` (observed), not `ExecutionError: not configured`.

Empty string still fails closed (round-1 holds for `""`); whitespace re-opens the hole.

---

### 4. MEDIUM — Contradictory `contact_name` + `contact_id` silently prefers name

**Where:** `app/providers/specs/cashctrl.yaml:54–68` + `app/providers/executor.py:145–155, 280–303`  
`contact_id` is only `fallback_arg` when step 0 is skipped; if `contact_name` is present, step 0 always wins.

**Defect:** Unconsumed-arg guard treats both as consumed; no conflict check. Explicit id is ignored without error.

**Concrete failure:**
1. Args: `{"contact_name": "Anna", "contact_id": 9201}` (Anna → 4827; 9201 = EWZ).
2. Resolve step runs on name → associateId 4827.
3. Result contact_ids = `{4827}` only (observed: 3 Anna rows), **not** EWZ’s journals.
4. Signed `query.executed` looks successful and correctly scoped by the model’s story, but contradicts the explicit `contact_id` the client/LLM also supplied.

---

### 5. MEDIUM — Missing / empty `base_url` does not fail closed

**Where:** `app/providers/executor.py:171`  
`base = (getattr(settings, self.spec.base_url_setting, "") or "").rstrip("/")`

**Defect:** Unlike secrets, empty or unknown setting attributes produce relative URLs and still build auth headers.

**Concrete failure:**
1. `cashctrl_api_base = ""` (or `base_url_setting` pointing at a non-existent settings attr).
2. `contact.lookup` → request URL `'/person/read.json'` with `Authorization: Bearer <key>` (observed).
3. Real transport: opaque `ExecutionError` (“missing http(s) protocol”), not a clear config refusal; worse, a mis-set `base_url_setting` can read any settings attribute (e.g. `secret_key`, `database_url`) into the URL string used for the call and error text.

---

### 6. MEDIUM — Money args for mutations are shape-weak (empty / scientific / padded strings)

**Where:** `app/providers/vocabulary.py:74–81` (`JournalCreateArgs.amount: str` only)

**Defect:** Comment claims “decimal string; never a float” (float is rejected — good), but empty/`1e10`/` 1.00 ` all validate and enter signed `mutation.proposed`.

**Concrete failure:** LLM args  
`{"date":"2026-01-01","amount":"","debit_account":1,"credit_account":2,"title":"t"}`  
→ preview signed with `amount: ""` (and similarly `"1e10"`, `" 1.00 "`). Confirm leg is deferred, but provenance already records a non-decimal “amount”.

---

### 7. LOW — HTTP-200 envelope check is Python-truthy, not boolean-strict

**Where:** `app/providers/executor.py:220–226`

**Defect:** `if _dig(raw, success_path):` — string `"false"` is truthy.

**Concrete failure:** Body `{"success": "false", "message": "nope", "data": {"id": "X"}}` → treated as success; result `{"id": "X"}` signed/returned. Boolean `false` / numeric `0` still fail loud (round-1 holds for real CashCtrl booleans).

---

### 8. LOW — Non-dict list elements dropped; truncated list signed complete

**Where:** `app/providers/executor.py:352`

**Defect:** `if isinstance(r, dict)` silently skips other elements.

**Concrete failure:**  
`{"items": [{"id":"A"}, "not-a-dict", {"id":"B"}, 3]}` → `count=2`, data `[A,B]`, no error. Authoritative signed list under-counts without pagination refusal.

---

### 9. LOW — Multi-tenant bindings without overrides still share one credential pool

**Where:** `app/providers/registry.py:51–54`, `app/core/config.py:58–64`

**Defect:** Overrides exist (round-1), but empty override dict silently falls back to global `cashctrl_api_key`. No production guard when `accounting_provider_bindings` has multiple tenants.

**Concrete failure:** Tenants T1, T2 both bound to `cashctrl`, only global key set → both executors use the same provider account/data. Cross-tenant exposure via shared backend identity (documented as MUST, not enforced).

---

## Round-1 fixes — re-break results

| Fix | Result after attack |
|---|---|
| Composite `steps` + empty short-circuit | **Holds.** Unknown name → `[]` / `count=0`; second HTTP step not called. |
| Unconsumed-arg guard | **Holds.** Filter not in binding → `ExecutionError` naming the arg. |
| HTTP-200 error envelope (boolean) | **Holds** for `false`/`0`; **weak** for string `"false"` (finding 7). |
| Pagination max / non-advancing cursor | **Holds** (covered by tests; logic sound). |
| Per-tenant credential overrides | **Mechanism holds**; whitespace and missing multi-tenant enforcement weak (3, 9). |
| Secrets fail-closed | **Holds for `""`/`None`**; **fails for whitespace** (finding 3). |
| Two-phase `query.requested` then execute | **Holds** by construction; mutations do not call transport. |
| Signed `mutation.proposed` + no execute | **Holds** (`executed=False`, no provider write). |
| `spec_version` in signed rows | **Holds** (tests + `base_after` / `CanonicalResult`). |

---

## Invariants — after genuine attack attempts

1. **Determinism / replay (executor result):** **Holds** for `(spec, op, args, transport)` — no clock/random in executor. Signed **audit row bytes** still include `datetime.now` in `audit.record` (pre-existing); identical audit bytes across runs are not true for the chain writer.
2. **Grammar cage (extra keys, unknown ops, float amount):** **Holds** at `validate_args`. Path-segment content is not caged (finding 2). Vendor names rejected by cage; still taught by Claude prompt (finding 1).
3. **Audit integrity (query two-phase, mutation preview only):** **Holds** on the dispatch path.
4. **Secrets in transport errors / fake in prod:** **Holds** — bearer not in `HttpxTransport` error text; fake only via DI override; `get_accounting_transport` → `HttpxTransport` only. SSRF via LLM-controlled `base_url` **not** possible; base comes from settings/spec.
5. **Tenant isolation (registry mutable state):** **Holds** — singleton holds immutable specs only; credentials resolved per call. Shared global key is config isolation failure (finding 9), not registry cache leakage.
6. **Doctrine (LLM behind gateway, canonical tools, provider as fact):** **Holds** for MockRouter + dispatch. **Broken for ClaudeRouter** prompt content (finding 1). Mutations not auto-applied.

**Also holds:** httpx `follow_redirects` default is `False` (no redirect-following SSRF via this client). Float `amount` rejected. OAuth2 raises not-implemented.

---

## Deferred (not filed)

OAuth2, DB-encrypted credentials, mutation confirm, live CashCtrl field-name correctness — as instructed.

---

## Verdict: **SHIP-WITH-FIXES**

**Not BLOCK:** Mock/default product path, round-1 safety rails (short-circuit, unconsumed args, envelope bool, pagination honesty, two-phase audit, mutation preview), and core cage behavior hold under attack.

**Not SHIP as-is:** Finding **1** makes the real LLM router non-functional and violates the canonical-tool doctrine; finding **2** is a load-bearing executor hole for any path-templated provider. Fix those before treating Claude or a second YAML adapter as production-ready. Findings 3–5 should land in the same hardening pass if multi-tenant / fail-closed claims matter.

**Suggested fix order:** (1) rewrite `intent_route.md` (+ version bump) to canonical ops including `journal.create` if needed; (2) encode/validate path segments + reject CRLF; (3) `val.strip()` (or reject whitespace) in `_secret`; (4) refuse empty `base_url`; (5) conflict on name+id or document fail-closed.
