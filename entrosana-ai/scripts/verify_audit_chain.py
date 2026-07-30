#!/usr/bin/env python3
"""Independent audit-chain verifier for `audit-demo.jsonl`.

Reads the JSONL log, recomputes each row's HMAC from
`HMAC(prev_hmac || canonical(payload))`, and compares it to the stored hmac.
Exit 0 iff every row checks out, non-zero otherwise.

Usage:

    python scripts/verify_audit_chain.py            # defaults to ./audit-demo.jsonl
    python scripts/verify_audit_chain.py PATH       # explicit path
    DEMO_AUDIT_KEY=<hex> python scripts/verify_audit_chain.py PATH

Without `DEMO_AUDIT_KEY` set, uses the same deterministic fallback key as
`app/dlm/demo_intent.py` so the POC verifies out-of-the-box.

A real production verifier would read the key from a hardware module or a
sealed secret store.  The two paths share the exact same crypto.

NOTE — scope of this script: it is the POC verifier for the demo JSONL log and
checks per-row `chained` + `signed` only. The AUTHORITATIVE, tamper-evident
verification for live data is `app.audit.service.verify_chain`, which
additionally enforces a signed monotonic `seq`, a persisted anchored head
(so tail-truncation is caught), and per-row `key_id` keyring lookup. Do not
treat a PASS here as equivalent to the DB chain's guarantees.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path


def _key() -> bytes:
    hex_key = os.environ.get("DEMO_AUDIT_KEY")
    if hex_key:
        return bytes.fromhex(hex_key)
    return hashlib.sha256(b"entrosana-demo-fixed-key").digest()


def _canonical(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def _sign(prev_hmac: str, payload: dict, key: bytes) -> str:
    msg = prev_hmac.encode() + _canonical(payload)
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def verify(log_path: Path) -> bool:
    key = _key()
    rows = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]

    prev = "GENESIS"
    all_ok = True
    for i, row in enumerate(rows):
        payload = {k: v for k, v in row.items() if k not in ("prev_hmac", "hmac")}
        expected = _sign(prev, payload, key)
        chained = row["prev_hmac"] == prev
        signed = row["hmac"] == expected
        ok = chained and signed
        all_ok = all_ok and ok

        mark = "PASS" if ok else "FAIL"
        if ok:
            detail = ""
        else:
            detail = (
                f"  (chained={chained}, signed={signed}; "
                f"expected hmac {expected[:12]}…, got {row['hmac'][:12]}…)"
            )
        print(f"  row {i}: [{mark}] prev={row['prev_hmac'][:12]}… hmac={row['hmac'][:12]}…{detail}")
        prev = row["hmac"]

    print(f"\noverall: {'PASS' if all_ok else 'FAIL'}")
    return all_ok


def main() -> int:
    log_path = Path(sys.argv[1] if len(sys.argv) > 1 else "audit-demo.jsonl")
    if not log_path.exists():
        print(f"error: log not found: {log_path}", file=sys.stderr)
        return 2
    return 0 if verify(log_path) else 1


if __name__ == "__main__":
    raise SystemExit(main())
