"""Accounting-provider abstraction — adapters as data, not code.

The DLM speaks a fixed, provider-neutral vocabulary (``app.providers.vocabulary``).
Each accounting backend (CashCtrl, bexio, Abacus, Banana, …) is a *declarative
spec* under ``app/providers/specs/<name>.yaml``, executed by one deterministic
engine (``app.providers.executor``). Nothing here calls an LLM: all API knowledge
is pinned in reviewed specs (author-time path-finding → hard-coded), so the runtime
is deterministic, auditable, and drivable by a small offline model whose only job
is prose → canonical op + args.

See ``docs/adr/0002-declarative-provider-specs.md``.
"""
