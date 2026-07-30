# audit/

The signed append-only log that anchors the audit-grade guarantee.

Every mutating service method in every module calls
`audit.record(actor, action, before, after, reasoning)`. Records are
HMAC-signed in a per-tenant chain so any post-hoc tampering breaks the
chain. `tests/test_audit_chain.py` exercises the invariant directly.

## Tables

- `audit_events` — every mutation in the system, with `prev_hmac → hmac`
  chain links per tenant
- `dlm_interactions` — every DLM call (input, output, model_version,
  prompt_version, retrieval_keys)

## Endpoints

- `GET  /api/v1/audit/events` — recent events for the calling tenant
- `POST /api/v1/audit/verify-chain` — re-verify the whole chain;
  returns `(ok, events_checked, first_bad_event_id)`

## Replay (planned)

`audit.replay(event_id)` reconstructs state-after-mutation from
state-before-mutation plus the recorded inputs. Because the DLM is
deterministic (temperature 0, pinned model + prompt versions,
deterministic retrieval order), any DLM-mediated decision is replayable
from the audit row alone.
