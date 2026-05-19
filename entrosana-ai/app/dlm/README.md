# dlm/

The thin wrapper that turns a stochastic LLM API into a deterministic agent.

## Doctrine

Every call to Claude (or whatever model) goes through `dlm.run(prompt_name,
input)`.  The wrapper:

1. Sets `temperature=0`
2. Pins the model version (`settings.dlm_model_version`)
3. Loads the prompt from a pinned version directory (`prompts/v0.1.0/...`)
4. Sorts any retrieval-augmented context by stable keys
5. Records the full interaction to `audit.dlm_interactions` with HMAC

`dlm.run()` is the ONLY way the rest of the app talks to the LLM.  Direct
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
