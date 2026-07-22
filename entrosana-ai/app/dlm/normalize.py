"""Deterministic intent normalization — Kronos-style input canonicalization.

Every user utterance passes through the same formula before routing or hashing.
Same raw intent (modulo whitespace/unicode variants) → same `intent_hash`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.dlm.base.core import fingerprint

# Swiss-style date: DD.MM.YYYY or DD/MM/YYYY → ISO YYYY-MM-DD (deterministic).
_DATE_DMY = re.compile(
    r"\b(?P<d>0?[1-9]|[12]\d|3[01])[./](?P<m>0?[1-9]|1[0-2])[./](?P<y>20\d{2})\b"
)


@dataclass(frozen=True, slots=True)
class CanonicalIntent:
    """Normalized user intent with a stable content hash."""

    raw: str
    normalized: str
    intent_hash: str

    @classmethod
    def from_raw(cls, text: str) -> CanonicalIntent:
        normalized = normalize_intent_text(text)
        return cls(
            raw=text,
            normalized=normalized,
            intent_hash=fingerprint({"normalized": normalized, "v": 1}),
        )


def normalize_intent_text(text: str) -> str:
    """Apply the canonical normalization pipeline (pure function).

    Steps:
      1. NFKC unicode normalization
      2. trim + collapse internal whitespace
      3. Swiss DMY dates → ISO (YYYY-MM-DD)
    """
    s = unicodedata.normalize("NFKC", text)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = _canonicalize_dates(s)
    return s


def _canonicalize_dates(text: str) -> str:
    def repl(m: re.Match[str]) -> str:
        d, mo, y = int(m.group("d")), int(m.group("m")), int(m.group("y"))
        return f"{y:04d}-{mo:02d}-{d:02d}"

    return _DATE_DMY.sub(repl, text)


def canonical_intent(text: str) -> CanonicalIntent:
    """Build a :class:`CanonicalIntent` from raw user text."""
    return CanonicalIntent.from_raw(text)
