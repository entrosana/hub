# Proof of concept

End-to-end demonstration of the entrosana doctrine: **user prose → intent →
CashCtrl API call → canonical data → signed audit row**.  Reproducible on
any machine with `uv` installed.  No database, no Docker, no API key
required for the default path.

## What this proves

1. **The audit chain is real.**  Every query against CashCtrl appends one
   HMAC-signed row to a hash-chained JSONL log.  An independent verifier
   re-derives every signature from on-disk bytes alone and catches any
   tampering with history.
2. **Inputs come from the system of record, not from an LLM.**  The LLM
   (or in offline mode, a regex router) only translates the user's prose
   into a structured tool call.  The data itself comes from CashCtrl.
3. **The DLM transducer is deterministic by theorem.**  Given the same
   `(Lexicon, Grammar)` artifact and the same input Features, it produces
   bit-identical Decisions across runs.  `example_school.py` exercises
   this end-to-end including the third-party `verify_replay` check.

## What this does NOT prove yet

- **No real CashCtrl call.**  Uses [`app/cashctrl/fake.py`](../app/cashctrl/fake.py),
  a deterministic in-memory backend with three contacts and five journal
  entries.  Real-CashCtrl client in [`app/cashctrl/client.py`](../app/cashctrl/client.py)
  covers `journal_list` + `journal_create` only — pending broadening to
  match the intent router's tool catalog.
- **No real LLM call by default.**  The MockRouter is a regex matcher over
  a small repertoire.  Pass `--use-claude` to invoke the real LLM via
  [`app/dlm/runner.py`](../app/dlm/runner.py); that path needs
  `ANTHROPIC_API_KEY` set.
- **No multi-tenant isolation.**  The demo writes a fixed `school-zh`
  tenant id.  Real `identity` module is on the Next-vertical list.
- **No DB persistence.**  Audit rows go to a JSONL file.  Production
  audit lives in `audit_events` (Postgres) via
  [`app/audit/service.py`](../app/audit/service.py), which uses the same
  chain primitives — see `tests/test_audit_chain.py`.

## Setup

```bash
git clone https://gitlab.com/Giansn/entrosana-ai.git
cd entrosana-ai
uv sync --extra dev
```

That's it.  No `.env`, no Postgres, no Anthropic key.

## Demo 1 — Read query

```bash
python -m app.dlm.demo_intent "pull May payments of Anna Müller"
```

Captured output:

```
user:   'pull May payments of Anna Müller'
router: MockRouter (regex)

intent → tool: cashctrl.journal_list
               args: {'contact_name': 'Anna Müller', 'date_from': '2026-05-01', 'date_to': '2026-05-31'}

cashctrl response (canonical truth):
  · 2026-05-04  JE-2026-0421  CHF    1450.00  Tuition Mai 2026 — Anna Müller
  · 2026-05-18  JE-2026-0445  CHF     120.00  Lehrmittel Mai 2026 — Anna Müller
  ── total: CHF 1570.00

audit row appended → audit-demo.jsonl
  prev_hmac: GENESIS
  hmac:      31a6fc4c6110614dd717dcbe6bc9a9f39f754b66411cfec04080111c6bf8e2f8

OK
```

What just happened:

1. `MockRouter` matched the prose to `cashctrl.journal_list` with three
   args (contact name + date range).  Deterministic by construction.
2. `FakeCashCtrl.journal_list` returned exactly the rows that meet
   those filters.  Sorted by `(date, id)` so the order is stable.
3. An audit row was appended.  Its `prev_hmac` is the literal `"GENESIS"`
   because this is the first row in the chain.

> The actual hashes on your machine will differ — the audit payload
> includes a `ts` (timestamp) field, so each run produces a fresh chain.
> The chain *structure* (prev_hmac linkage, GENESIS anchor, HMAC over
> canonical bytes) is invariant.

## Demo 2 — Specific lookup

```bash
python -m app.dlm.demo_intent "show me journal JE-2026-0445"
```

```
user:   'show me journal JE-2026-0445'
router: MockRouter (regex)

intent → tool: cashctrl.journal_get
               args: {'id': 'JE-2026-0445'}

cashctrl response (canonical truth):
               id: JE-2026-0445
             date: 2026-05-18
       contact_id: 4827
            title: Lehrmittel Mai 2026 — Anna Müller
           amount: 120.00
         currency: CHF
    debit_account: 4500
   credit_account: 1100

audit row appended → audit-demo.jsonl
  prev_hmac: 31a6fc4c6110614dd717dcbe6bc9a9f39f754b66411cfec04080111c6bf8e2f8
  hmac:      207f7100f0516d99d0d0bc2f2682f2373bc432e95ab9e61575b3765b79baffb5

OK
```

Notice: `prev_hmac` of row 2 matches `hmac` of row 1 exactly.  The chain
is linked.

## Demo 3 — Independent chain verification

```bash
python scripts/verify_audit_chain.py audit-demo.jsonl
```

```
  row 0: [PASS] prev=GENESIS… hmac=31a6fc4c6110…
  row 1: [PASS] prev=31a6fc4c6110… hmac=207f7100f051…

overall: PASS
```

The verifier is **independent code** in
[`scripts/verify_audit_chain.py`](../scripts/verify_audit_chain.py) — it
shares no logic with `demo_intent.py` beyond the public crypto primitives.
For each row it recomputes `HMAC(prev_hmac || canonical(payload))` and
compares it to the stored `hmac`.  Match on every row → chain intact.

This is what a revisor (or the school's accountant, or an external
auditor) runs to attest that no event has been altered since signing.

## Demo 4 — Tamper detection

Suppose someone edits the on-disk JSONL to change row 0's `result_count`
from 2 to 999 but doesn't touch the `hmac` field.

```python
# tamper
rows = [json.loads(l) for l in open("audit-demo.jsonl") if l.strip()]
rows[0]["result_count"] = 999
with open("audit-demo.jsonl", "w") as f:
    for r in rows: f.write(json.dumps(r, sort_keys=True) + "\n")
```

Re-run the verifier:

```
  row 0: [FAIL] prev=GENESIS… hmac=31a6fc4c6110…  (chained=True, signed=False;
                expected hmac 05b0fe4009f2…, got 31a6fc4c6110…)
  row 1: [PASS] prev=31a6fc4c6110… hmac=207f7100f051…

overall: FAIL
```

The verifier recomputed what row 0's `hmac` *should be* given its current
on-disk payload (`05b0fe4009f2…`) and found it does not match the stored
`31a6fc4c6110…`.  The tamper is caught — exit code non-zero.

A determined adversary could also recompute row 0's `hmac` to match the
new payload, but then row 1's `prev_hmac` (which is bound to the
*original* row 0 hmac) would no longer match.  Recomputing row 1 too
requires the signing key.  The chain is only as forgeable as the key is
exposed.

## Demo 5 — The DLM transducer

The above demos exercise the audit-chain and intent-routing layers.  The
DLM transducer itself — the deterministic `(Lexicon, Grammar)` engine in
[`app/dlm/base/core.py`](../app/dlm/base/core.py) — is exercised by
the end-to-end school example:

```bash
python -m app.dlm.base.example_school
```

```
tier:       second
confidence: 0.90
value:      {'amount': '412.50', 'amt': '412.50', 'currency': 'CHF', 'doc_type': 'RECHNUNG'}
run_id:     5530572dfdd53e052abbc05b
dlm_fp:     bfca93a4e2a4dcd2…

action kind: booking
action ready for Sink.commit(action)

audit chain:
  [PASS] signature: HMAC validated
  [PASS] content: input matches recorded hash
  [PASS] replay: exact (same fingerprint, theorem)
```

The `replay: exact (same fingerprint, theorem)` line is the key claim:
the DLM is a transducer, and rerunning it on the same Features under the
same `dlm_fp` produces bit-identical output.  This is what
`verify_replay.py` validates for a stored Decision against current
artifacts.

## Reading one audit row

```json
{
  "prev_hmac":    "GENESIS",
  "hmac":         "31a6fc4c6110614dd717dcbe6bc9a9f39f754b66411cfec04080111c6bf8e2f8",
  "ts":           "2026-05-19T17:42:31+00:00",
  "tenant_id":    "school-zh",
  "actor_id":     "demo-user",
  "action":       "query.executed",
  "user_input":   "pull May payments of Anna Müller",
  "tool_call":    {"tool": "cashctrl.journal_list",
                   "args": {"contact_name": "Anna Müller",
                            "date_from": "2026-05-01",
                            "date_to":   "2026-05-31"}},
  "result_count": 2,
  "provenance":   "record",
  "source":       "cashctrl"
}
```

Field-by-field:

| field            | meaning                                                       |
|------------------|---------------------------------------------------------------|
| `prev_hmac`      | HMAC of the previous row (or `"GENESIS"` for the first)        |
| `hmac`           | HMAC of `prev_hmac || canonical(payload)`                      |
| `ts`             | UTC timestamp of the audit event                              |
| `tenant_id`      | which school this belonged to                                  |
| `actor_id`       | who initiated the action (would be a JWT-resolved user in prod)|
| `action`         | event kind — used to filter audit history by type              |
| `user_input`     | the original natural-language prose                            |
| `tool_call`      | the concrete CashCtrl API call that was executed              |
| `result_count`   | how many rows CashCtrl returned                                |
| `provenance`     | `"record"` ⇒ deterministic source.  See [Input provenance](../README.md#input-provenance) |
| `source`         | concrete backend — `"cashctrl"` here; could be `"provider:swissdec"` etc |

A revisor reading the chain can answer, for any historical row: *who did
what, when, with what canonical input, against which system of record* —
and confirm the row has not been edited since.

## Files in the POC

| file                                            | role                                       |
|-------------------------------------------------|--------------------------------------------|
| [`app/dlm/demo_intent.py`](../app/dlm/demo_intent.py)   | CLI: prose → intent → CashCtrl → signed row |
| [`app/dlm/intent.py`](../app/dlm/intent.py)             | `MockRouter` + `ClaudeRouter`              |
| [`app/cashctrl/fake.py`](../app/cashctrl/fake.py)       | Deterministic in-memory CashCtrl backend   |
| [`app/dlm/prompts/v0.1.0/intent_route.md`](../app/dlm/prompts/v0.1.0/intent_route.md) | Pinned LLM prompt (when `--use-claude`)    |
| [`scripts/verify_audit_chain.py`](../scripts/verify_audit_chain.py) | Independent chain verifier                 |
| [`app/dlm/base/example_school.py`](../app/dlm/base/example_school.py) | DLM transducer end-to-end                  |
| [`app/dlm/base/verify_replay.py`](../app/dlm/base/verify_replay.py)   | Third-party Decision replay CLI            |
| [`tests/test_audit_chain.py`](../tests/test_audit_chain.py)           | Cryptographic property tests (9 cases)     |

## Next-step proofs to add

1. **Real CashCtrl integration** — broaden `app/cashctrl/client.py` to
   match the intent router's tool catalog.  Run the POC against a real
   tenant or sandbox.
2. **Structured-output enforcement** — `app/dlm/runner.py` should expose
   `run_structured(prompt, schema)` that validates the LLM's JSON
   against the expected shape and rejects free text.  Without it, the
   ClaudeRouter relies on the model's compliance.
3. **Provenance through to CashCtrl write-side** — `CashCtrlSink.commit`
   already writes `dlm_fp`, `confidence`, `audit_run_id` to CashCtrl
   custom fields.  Extend with `provenance` and `provider` so a revisor
   reading the booking in CashCtrl alone can tell which fields were
   attested by entrosana vs. third-party providers.
4. **DB-backed audit** — wire `demo_intent.py` through `app/audit/service.py`
   so the chain lives in Postgres, not a JSONL file.  Same crypto, real
   persistence.
