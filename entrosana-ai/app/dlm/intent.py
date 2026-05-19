"""User prose → structured CashCtrl tool call.

This is the only LLM-touching surface that produces values feeding the audit
chain — and even then only INDIRECTLY: the LLM emits a tool call (verb +
structured args), which is then executed against CashCtrl.  CashCtrl's
response is the source of fact.  The LLM never invents data.

Two backends:

- `MockRouter` — regex-based, deterministic, no network.  Used in tests and
  by the offline POC.  Honest about its limitations: it does not understand
  intent, only pattern-matches a small set of phrasings.

- `ClaudeRouter` — calls Claude via `app.dlm.runner.run` with the pinned
  `intent_route` prompt bundle.  Requires `ANTHROPIC_API_KEY` and a present
  prompt directory on disk.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool: str
    args: dict


class IntentRouter(Protocol):
    async def route(self, user_input: str) -> ToolCall: ...


# ────────────────────────────────────────────────────────────────────────
# Mock router — regex over a small repertoire.  Deterministic by design.
# ────────────────────────────────────────────────────────────────────────

_MONTHS = {
    # English
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
    # German (unique spellings only; shared ones like "april" stay above)
    "januar": "01",
    "februar": "02",
    "märz": "03",
    "mai": "05",
    "juni": "06",
    "juli": "07",
    "oktober": "10",
    "dezember": "12",
}


def _month_range(text: str, year: str = "2026") -> tuple[str, str] | None:
    for name, num in _MONTHS.items():
        if re.search(rf"\b{name}\b", text.lower()):
            from calendar import monthrange

            last = monthrange(int(year), int(num))[1]
            return f"{year}-{num}-01", f"{year}-{num}-{last:02d}"
    return None


class MockRouter:
    """Regex-based router.  Same input → same tool call, every time."""

    async def route(self, user_input: str) -> ToolCall:
        s = user_input.lower()

        # contact lookup: "contact 4827" or "show contact <id>"
        if m := re.search(r"\bcontact\s+(\d+)\b", s):
            return ToolCall("cashctrl.contact_lookup", {"id": int(m.group(1))})

        # journal_get: "JE-YYYY-NNNN"
        if m := re.search(r"\b(JE-\d{4}-\d{3,})\b", user_input):
            return ToolCall("cashctrl.journal_get", {"id": m.group(1)})

        # journal_list with contact name: "payments of <name>"
        if m := re.search(
            r"(?:payments?|bookings?|entries?)\s+(?:of|for|from)\s+([A-ZÄÖÜ][\wäöüÄÖÜß\s\-\.]+?)(?:\s+in\s+|\s+from\s+|\s*$)",
            user_input,
        ):
            args: dict = {"contact_name": m.group(1).strip()}
            rng = _month_range(s)
            if rng:
                args["date_from"], args["date_to"] = rng
            return ToolCall("cashctrl.journal_list", args)

        # journal_list with explicit date range, no contact
        rng = _month_range(s)
        if rng:
            return ToolCall("cashctrl.journal_list", {"date_from": rng[0], "date_to": rng[1]})

        # default: list latest 10
        return ToolCall("cashctrl.journal_list", {})


# ────────────────────────────────────────────────────────────────────────
# Claude router — wraps app.dlm.runner.run for real LLM intent translation
# ────────────────────────────────────────────────────────────────────────


class ClaudeRouter:
    """LLM-backed router.  Calls Claude via the pinned DLM wrapper."""

    async def route(self, user_input: str) -> ToolCall:
        from app.dlm.runner import run  # lazy import

        result = await run("intent_route", {"user_input": user_input})
        return _parse_tool_call(result["output"])


def _parse_tool_call(text: str) -> ToolCall:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.DOTALL)
        text = re.sub(r"\s*```\s*$", "", text, flags=re.DOTALL)
    obj = json.loads(text)
    if not isinstance(obj, dict) or "tool" not in obj:
        raise ValueError(f"LLM did not return a tool-call JSON: {text[:200]!r}")
    return ToolCall(tool=obj["tool"], args=obj.get("args", {}) or {})
