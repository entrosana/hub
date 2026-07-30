"""Unit tests for intent normalization."""

from app.dlm.normalize import canonical_intent, normalize_intent_text


def test_nfkc_and_whitespace():
    raw = "  Pull   May   payments  "
    norm = normalize_intent_text(raw)
    assert norm == "Pull May payments"


def test_swiss_date_canonicalization():
    norm = normalize_intent_text("entries from 01.05.2026 to 31.05.2026")
    assert "2026-05-01" in norm
    assert "2026-05-31" in norm


def test_intent_hash_stable_for_whitespace_variants():
    a = canonical_intent("Pull May payments of Anna Müller")
    b = canonical_intent("  Pull   May payments of Anna Müller  ")
    assert a.normalized == b.normalized
    assert a.intent_hash == b.intent_hash


def test_unicode_nfkc():
    composed = "\ufb01le"  # ﬁle
    decomposed = "file"
    assert normalize_intent_text(composed) == normalize_intent_text(decomposed)
