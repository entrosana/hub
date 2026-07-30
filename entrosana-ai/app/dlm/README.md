# dlm/

The thin wrapper that turns a stochastic LLM API into a deterministic agent.

## Entry point

**Use `DLMGateway`** (`app/dlm/gateway.py`) — the process singleton.  Import via:

```python
from app.dlm import gateway, DLMGateway
```

`gateway.route_intent(text)` normalizes prose, routes to a tool call, and
records `intent_hash` + `env_fp` on audit rows.  `runner.run()` is internal.

## Doctrine

Every call to Claude (or whatever model) goes through `DLMGateway.run_llm()` /
`route_intent()`.  The wrapper:

1. Normalizes input (`app/dlm/normalize.py` — NFKC, whitespace, Swiss dates)
2. Sets `temperature=0`
3. Pins the model version (`settings.dlm_model_version`)
4. Loads the prompt from a pinned version directory (`prompts/v0.1.0/...`)
5. Sorts any retrieval-augmented context by stable keys
6. Records the full interaction to `audit.dlm_interactions` with HMAC

`DLMGateway` is the ONLY way the rest of the app talks to the LLM.  Direct
`anthropic.Anthropic()` calls are forbidden (enforced via lint rule).

## Prompt versioning

```
app/dlm/prompts/
  v0.1.0/
    booking_propose.md          # accounting/service.py uses this
    document_classify.md        # documents/service.py uses this
    contract_summarise.md       # contracts/service.py uses this
  v0.2.0/
    ...
```

The active version is `settings.dlm_prompt_version`.  When promoting, write a
new vX.Y.Z/ folder, update the env var, redeploy.  Old versions stay so
historical interactions can be replayed.
