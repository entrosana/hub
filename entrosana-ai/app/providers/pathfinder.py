"""Author-time API path-finder — assists writing a new provider spec.

This is the "API path-finding" step: given a backend's OpenAPI document and the
canonical vocabulary, it proposes which endpoint (path + method) implements each
canonical op, ranked by a transparent keyword heuristic, and prints a spec
skeleton to fill in. It is **offline and LLM-free** (deterministic, runs anywhere)
and it is **advisory**: a human reviews the proposal, completes the query/response
mappings, and only then is the result hard-coded into ``specs/<name>.yaml`` and
gated by the contract tests.

    python -m app.providers.pathfinder path/to/openapi.json
    python -m app.providers.pathfinder openapi.json --op journal.list --top 5

It proposes the *endpoint*; it does not invent field mappings (those need the
schema + a human). That is the deliberate split that keeps runtime deterministic:
all the guessing happens here, at author time, under review — never at runtime.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.providers.vocabulary import CANONICAL_OPS

# Synonyms let the heuristic match vendor vocabulary to canonical ops. The kernel
# ships none: domain packs register their own object words. This only affects
# author-time ranking, never runtime behaviour.
OBJECT_SYNONYMS: dict[str, set[str]] = {}


def register_object_synonyms(**objects: set[str]) -> None:
    """Add object-word synonyms for a domain, e.g. ``contact={"person", ...}``."""

    for name, words in objects.items():
        OBJECT_SYNONYMS.setdefault(name, set()).update(words)
_VERB_SYNONYMS: dict[str, set[str]] = {
    "lookup": {"lookup", "read", "get", "show", "find", "search", "detail", "retrieve"},
    "list": {"list", "index", "all", "search", "query", "browse"},
    "get": {"get", "read", "show", "detail", "retrieve", "fetch"},
    "create": {"create", "add", "new", "post", "insert", "make"},
}
_VERB_METHOD: dict[str, set[str]] = {
    "lookup": {"GET"},
    "list": {"GET"},
    "get": {"GET"},
    "create": {"POST", "PUT"},
}
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")
_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(*parts: str) -> set[str]:
    out: set[str] = set()
    for p in parts:
        if p:
            out.update(_TOKEN.findall(p.lower()))
    return out


@dataclass(slots=True)
class Candidate:
    op: str
    method: str
    path: str
    score: int
    operation_id: str = ""
    summary: str = ""
    param_names: list[str] = field(default_factory=list)


def _op_terms(op_name: str) -> tuple[set[str], set[str], str]:
    """(object synonyms, verb synonyms, verb) for a canonical op like 'journal.list'."""
    obj, _, verb = op_name.partition(".")
    return OBJECT_SYNONYMS.get(obj, {obj}), _VERB_SYNONYMS.get(verb, {verb}), verb


def _score(op_name: str, method: str, path: str, op_obj: dict) -> Candidate:
    obj_syn, verb_syn, verb = _op_terms(op_name)
    op_id = str(op_obj.get("operationId", ""))
    summary = str(op_obj.get("summary", "") or op_obj.get("description", ""))
    ep_tokens = _tokens(path, op_id, summary)

    score = 0
    if ep_tokens & obj_syn:
        score += 2  # object match is the strong signal
    if ep_tokens & verb_syn:
        score += 2  # verb match
    if method.upper() in _VERB_METHOD.get(verb, set()):
        score += 1  # HTTP method agrees with the verb's nature
    params = [p.get("name", "") for p in op_obj.get("parameters", []) if isinstance(p, dict)]
    return Candidate(op_name, method.upper(), path, score, op_id, summary, params)


def propose_bindings(
    openapi: dict, ops: list[str] | None = None, top: int = 3
) -> dict[str, list[Candidate]]:
    """Rank endpoint candidates for each canonical op. Deterministic."""
    ops = ops or list(CANONICAL_OPS)
    paths = openapi.get("paths", {})
    endpoints: list[tuple[str, str, dict]] = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method in _HTTP_METHODS:
            if isinstance(item.get(method), dict):
                endpoints.append((method, path, item[method]))

    out: dict[str, list[Candidate]] = {}
    for op_name in ops:
        cands = [_score(op_name, m, p, o) for (m, p, o) in endpoints]
        cands = [c for c in cands if c.score > 0]
        # stable ranking: score desc, then shortest path, then path alpha
        cands.sort(key=lambda c: (-c.score, len(c.path), c.path))
        out[op_name] = cands[:top]
    return out


def render_proposal(proposals: dict[str, list[Candidate]]) -> str:
    lines = [
        "# path-finder proposal — REVIEW REQUIRED before hard-coding.",
        "# The endpoint is a suggestion; you must fill query/response mappings.",
        "operations:",
    ]
    for op_name, cands in proposals.items():
        kind = CANONICAL_OPS[op_name].kind.value if op_name in CANONICAL_OPS else "?"
        lines.append(f"\n  {op_name}:   # kind={kind}")
        if not cands:
            lines.append("    # (no candidate endpoint matched — map by hand)")
            continue
        best = cands[0]
        lines.append("    http:")
        lines.append(f"      method: {best.method}")
        lines.append(f"      path: {best.path}")
        lines.append("      query: {}       # TODO: map canonical args -> params")
        if best.param_names:
            lines.append(f"      # endpoint params: {', '.join(best.param_names)}")
        lines.append("      response:")
        lines.append(
            '        list_path: ""  # TODO'
            if _is_list(op_name)
            else '        item_path: ""  # TODO'
        )
        lines.append("        fields: {}     # TODO: canonical_field: provider.path")
        if len(cands) > 1:
            alts = "; ".join(f"{c.method} {c.path} (score {c.score})" for c in cands[1:])
            lines.append(f"    # alternatives: {alts}")
        if best.summary:
            lines.append(f"    # matched: {best.summary[:100]}")
    return "\n".join(lines) + "\n"


def _is_list(op_name: str) -> bool:
    from app.providers.vocabulary import ResultKind

    op = CANONICAL_OPS.get(op_name)
    return bool(op and op.result == ResultKind.LIST)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("openapi", type=Path, help="Path to the provider's OpenAPI JSON document.")
    ap.add_argument("--op", action="append", help="Restrict to this canonical op (repeatable).")
    ap.add_argument("--top", type=int, default=3, help="Candidates to show per op.")
    args = ap.parse_args(argv)

    try:
        doc = json.loads(args.openapi.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"error: cannot read OpenAPI doc: {e}", file=sys.stderr)
        return 2
    unknown = set(args.op or []) - set(CANONICAL_OPS)
    if unknown:
        print(f"error: unknown canonical op(s): {sorted(unknown)}", file=sys.stderr)
        return 2

    proposals = propose_bindings(doc, ops=args.op, top=args.top)
    print(render_proposal(proposals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
