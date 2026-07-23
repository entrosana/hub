"""POC: prose → intent → CashCtrl → signed audit row.

End-to-end demonstration of the new doctrine.  No DB, no Docker, no network
required when running with the default MockRouter.

Run:

    # default — offline mock router, deterministic
    python -m app.dlm.demo_intent "pull May payments of Anna Müller"

    # real Claude (needs ANTHROPIC_API_KEY + the v0.1.0 prompt bundle)
    python -m app.dlm.demo_intent --use-claude "show me journal JE-2026-0445"

Each invocation appends ONE row to `audit-demo.jsonl` (in the cwd by default,
override with `AUDIT_LOG=<path>`).  Every row carries:

    - tenant_id, actor_id, ts          — who, when
    - user_input, tool_call            — what was asked, how it was translated
    - result_count                     — what CashCtrl returned
    - provenance: "record"             — system of record
    - source: "cashctrl"               — concrete provider
    - prev_hmac, hmac                  — hash-chain link

The chain bootstraps at "GENESIS".  Tampering with any earlier row breaks
every subsequent HMAC.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from app.dlm.gateway import DLMGateway
from app.dlm.intent import ToolCall
from app.providers.executor import ProviderExecutor
from app.providers.fake import FakeCashCtrlTransport
from app.providers.registry import ProviderRegistry
from app.providers.vocabulary import validate_args

AUDIT_LOG = Path(os.environ.get("AUDIT_LOG", "audit-demo.jsonl"))
GENESIS = "GENESIS"


# ── audit chain helpers ─────────────────────────────────────────────────


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sign(prev_hmac: str, payload: dict, key: bytes) -> str:
    msg = prev_hmac.encode() + _canonical(payload)
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def _last_hmac(log: Path) -> str:
    if not log.exists():
        return GENESIS
    last = GENESIS
    for line in log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            last = json.loads(line)["hmac"]
    return last


def append_audit(payload: dict, key: bytes, log: Path = AUDIT_LOG) -> tuple[str, str]:
    """Append a signed row; return (prev_hmac, hmac)."""
    prev = _last_hmac(log)
    sig = _sign(prev, payload, key)
    row = {"prev_hmac": prev, "hmac": sig, **payload}
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return prev, sig


# ── demo flow ───────────────────────────────────────────────────────────


async def run_demo(
    user_input: str, *, use_claude: bool, actor_id: str, tenant_id: str, key: bytes, log: Path
) -> int:
    DLMGateway.reset()
    gw = DLMGateway.for_claude() if use_claude else DLMGateway.for_mock()

    print(f"user:   {user_input!r}")
    print(f"router: {'ClaudeRouter (via DLMGateway)' if use_claude else 'MockRouter (regex)'}")
    print()

    # 1) normalize → intent → tool call
    routed = await gw.route_intent(user_input)
    print(f"normalized: {routed.canonical.normalized!r}")
    print(f"intent_hash: {routed.canonical.intent_hash[:16]}…")
    tc = ToolCall(routed.tool, routed.args)
    print(f"intent → tool: {tc.tool}")
    print(f"               args: {tc.args}")
    print()

    # 2) dispatch to the tenant's accounting provider (system of record).
    #    Same code path for CashCtrl, bexio, or any backend — the executor runs
    #    whichever declarative spec the tenant is bound to. The demo uses the
    #    offline fake transport (no network) with an explicit dummy credential:
    #    the executor fails closed on unset secrets, and the fake ignores auth.
    registry = ProviderRegistry()
    executor = ProviderExecutor(
        registry.resolve(tenant_id),
        FakeCashCtrlTransport(),
        credential_overrides={
            "cashctrl_api_key": "demo-offline-key",
            "cashctrl_api_base": "http://cashctrl.demo-offline.test",
        },
    )
    try:
        vargs = validate_args(tc.tool, tc.args)  # grammar cage
        cres = await executor.execute(tc.tool, vargs.model_dump())
    except Exception as e:  # noqa: BLE001 — POC surfaces any failure to stderr
        print(f"error: {e}", file=sys.stderr)
        return 2
    result = cres.data

    # 3) show
    print(f"{cres.source} response (canonical truth):")
    if isinstance(result, list):
        if not result:
            print("  (no entries match)")
        else:
            for r in result:
                print(f"  · {r['date']}  {r['id']}  CHF {r['amount']:>10}  {r['title']}")
            total = sum((Decimal(str(r["amount"])) for r in result), Decimal("0"))
            print(f"  ── total: CHF {total}")
    elif result is None:
        print("  (not found)")
    else:
        for k, v in result.items():
            print(f"  {k:>15}: {v}")
    print()

    # 4) sign the audit event
    audit_row = gw.build_query_audit(
        routed,
        result_count=cres.count,
        tenant_id=tenant_id,
        actor_id=actor_id,
        source=cres.source,
    )
    audit_payload = {
        "ts": audit_row.ts,
        "tenant_id": audit_row.tenant_id,
        "actor_id": audit_row.actor_id,
        "action": audit_row.action,
        "user_input": audit_row.user_input,
        "normalized_input": audit_row.normalized_input,
        "intent_hash": audit_row.intent_hash,
        "tool_call": audit_row.tool_call,
        "result_count": audit_row.result_count,
        "provenance": audit_row.provenance,
        "source": audit_row.source,
        "env_fp": audit_row.env_fp,
    }
    prev, sig = append_audit(audit_payload, key, log)

    print(f"audit row appended → {log}")
    print(f"  prev_hmac: {prev}")
    print(f"  hmac:      {sig}")
    print()
    print("OK")
    return 0


def _resolve_key() -> bytes:
    hex_key = os.environ.get("DEMO_AUDIT_KEY")
    if hex_key:
        return bytes.fromhex(hex_key)
    # deterministic fallback so the POC runs out-of-the-box
    return hashlib.sha256(b"entrosana-demo-fixed-key").digest()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="POC: prose → intent → CashCtrl → signed audit row.",
    )
    ap.add_argument(
        "user_input",
        nargs="+",
        help='Natural-language request, e.g. "pull May payments of Anna Müller".',
    )
    ap.add_argument(
        "--use-claude",
        action="store_true",
        help="Use the LLM intent router (requires ANTHROPIC_API_KEY).",
    )
    ap.add_argument("--tenant", default=os.environ.get("TENANT_ID", "school-zh"))
    ap.add_argument("--actor", default=os.environ.get("ACTOR_ID", "demo-user"))
    ap.add_argument("--log", type=Path, default=AUDIT_LOG)
    args = ap.parse_args()

    return asyncio.run(
        run_demo(
            " ".join(args.user_input),
            use_claude=args.use_claude,
            actor_id=args.actor,
            tenant_id=args.tenant,
            key=_resolve_key(),
            log=args.log,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
