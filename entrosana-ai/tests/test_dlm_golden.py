"""Golden regression tests for the DLM transducer and intent pipeline.

Mirrors Kronos's ``test_kronos_regression.py``: pinned artifacts, fixed inputs,
expected outputs on disk.  If ``dlm.fp`` is unchanged, replay must be exact.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from app.dlm.base.core import Features, Provenance, Verifier, audit_chain
from app.dlm.base.example_school import build_agent, dlm
from app.dlm.gateway import DLMGateway
from app.dlm.normalize import canonical_intent

GOLDEN = Path(__file__).parent / "golden"
KEY_HEX = "ab" * 32


def _load_json(name: str) -> dict:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def _features_from_golden(data: dict) -> Features:
    return Features(
        doc_id=data["doc_id"],
        content_hash=data["content_hash"],
        fields=tuple(sorted(data["fields"].items())),
        provenance=Provenance(data.get("provenance", "record")),
        provider=data.get("provider", ""),
    )


def test_transducer_propose_matches_golden():
    """Same Features + same dlm.fp → same candidate (replay theorem)."""
    expected = _load_json("inv-ewz-001.propose.json")
    feat = _features_from_golden(_load_json("inv-ewz-001.features.json"))

    assert dlm.fp == expected["dlm_fp"], "DLM fingerprint drift — update golden or witness"

    candidates = dlm.propose(feat)
    assert candidates, "expected at least one candidate"
    top = candidates[0]

    assert top.template_id == expected["template_id"]
    assert dict(top.bindings) == expected["bindings"]
    assert str(top.confidence) == expected["confidence"]
    assert list(top.reasons) == expected["reasons"]


def test_audit_chain_replay_theorem():
    """Full verify chain: signature + content + exact replay."""
    feat = _features_from_golden(_load_json("inv-ewz-001.features.json"))
    agent = build_agent(KEY_HEX)
    decision = agent.propose(feat)
    verifier = Verifier({"2026-q2": bytes.fromhex(KEY_HEX)})

    results = audit_chain(decision, features=feat, dlm=dlm, verifier=verifier)
    for check, (passed, reason) in results.items():
        assert passed, f"{check} failed: {reason}"


def test_intent_normalize_golden():
    """Normalization formula is stable across unicode/whitespace variants."""
    expected = _load_json("intent_normalize.json")
    for raw, want in expected.items():
        ci = canonical_intent(raw)
        assert ci.normalized == want["normalized"], raw
        assert ci.intent_hash == want["intent_hash"], raw


@pytest.mark.asyncio
async def test_intent_route_mock_golden():
    """MockRouter routes normalized intents to pinned tool calls."""
    expected = _load_json("intent_route_mock.json")
    DLMGateway.reset()
    gw = DLMGateway.for_mock()

    for raw, want in expected.items():
        routed = await gw.route_intent(raw)
        assert routed.tool == want["tool"], raw
        assert routed.args == want["args"], raw
        assert routed.canonical.intent_hash == want["intent_hash"], raw


def test_gateway_singleton():
    DLMGateway.reset()
    a = DLMGateway.instance()
    b = DLMGateway.instance()
    assert a is b
    DLMGateway.reset()
    assert DLMGateway._instance is None


def test_gateway_verify_delegates_to_audit_chain():
    feat = _features_from_golden(_load_json("inv-ewz-001.features.json"))
    agent = build_agent(KEY_HEX)
    decision = agent.propose(feat)
    verifier = Verifier({"2026-q2": bytes.fromhex(KEY_HEX)})

    DLMGateway.reset()
    gw = DLMGateway.for_mock()
    results = gw.verify(decision, features=feat, dlm=dlm, verifier=verifier)
    assert all(ok for ok, _ in results.values())
