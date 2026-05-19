"""CLI: verify a stored Decision against its Features and the current DLM.

Independent third-party check. Reads decision + features from JSON files,
imports the DLM artifacts from a module, runs the full audit chain.

Exit code 0 if every check passes, 1 otherwise.

Example:
    DLM_KEY=$(cat ~/.dlm/key.hex) \\
    python -m app.dlm.base.verify_replay \\
        --decision decisions/inv-001.json \\
        --features features/inv-001.json \\
        --key-id 2026-q2 \\
        --dlm-module app.dlm.base.example_school
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .core import (
    DLM,
    Candidate,
    Decision,
    Features,
    Provenance,
    Tier,
    Verifier,
    audit_chain,
)


def load_decision(path: Path) -> Decision:
    d = json.loads(path.read_text())
    return Decision(
        document_id=d["document_id"],
        content_hash=d["content_hash"],
        value=tuple(tuple(kv) for kv in d["value"]),
        confidence=Decimal(d["confidence"]),
        alternatives=tuple(
            Candidate(
                template_id=c["template_id"],
                bindings=tuple(tuple(kv) for kv in c["bindings"]),
                confidence=Decimal(c["confidence"]),
                reasons=tuple(c["reasons"]),
            )
            for c in d["alternatives"]
        ),
        tier_required=Tier(d["tier_required"]),
        run_id=d["run_id"],
        dlm_fp=d["dlm_fp"],
        tenant_id=d["tenant_id"],
        signed_at=datetime.fromisoformat(d["signed_at"]),
        signature=d["signature"],
        provenance=Provenance(d.get("provenance", "record")),
        provider=d.get("provider", ""),
    )


def load_features(path: Path) -> Features:
    f = json.loads(path.read_text())
    return Features.of(
        doc_id=f["doc_id"],
        content_hash=f["content_hash"],
        fields=f["fields"],
        provenance=Provenance(f.get("provenance", "record")),
        provider=f.get("provider", ""),
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verify a DLM decision against current artifacts.",
    )
    ap.add_argument(
        "--decision",
        type=Path,
        required=True,
        help="Path to decision JSON (as recorded by AuditTrail).",
    )
    ap.add_argument(
        "--features", type=Path, required=True, help="Path to features JSON used at decision time."
    )
    ap.add_argument(
        "--key-id", type=str, required=True, help="Key id the signature was minted under."
    )
    ap.add_argument(
        "--dlm-module",
        type=str,
        required=True,
        help="Importable module exposing `dlm: DLM` at top level.",
    )
    args = ap.parse_args()

    key_hex = os.environ.get("DLM_KEY")
    if not key_hex:
        print("error: DLM_KEY env var (hex) is required", file=sys.stderr)
        return 2

    decision = load_decision(args.decision)
    features = load_features(args.features)

    mod = importlib.import_module(args.dlm_module)
    dlm: DLM = getattr(mod, "dlm", None) or mod.build_dlm()

    verifier = Verifier({args.key_id: bytes.fromhex(key_hex)})
    results = audit_chain(decision, features=features, dlm=dlm, verifier=verifier)

    ok = True
    for check, (passed, reason) in results.items():
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {check}: {reason}")
        if not passed:
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
