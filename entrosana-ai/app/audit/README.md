# audit/

The signed append-only log that's the heart of the audit-grade guarantee.

Every mutating service method in every module calls `audit.record(actor, action,
before, after, reasoning)`.  Records are HMAC-signed in a chain so any
tampering breaks the chain.

## Tables

- `audit_events` — every mutation in the system
- `dlm_interactions` — every DLM call (input, output, model_version, prompt_version)

## Replay

`audit.replay(event_id)` reconstructs the state-after-mutation from the
state-before-mutation + the recorded inputs.  Same input always yields same
output (DLM doctrine) so any DLM-mediated decision is replayable.
