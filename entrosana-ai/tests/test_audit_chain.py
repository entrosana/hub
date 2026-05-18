"""Audit-chain HMAC verification.  Foundational -- the DLM doctrine depends on this."""
# Stub.  Real test will:
#   1. record() three events
#   2. verify_chain() -> (True, 3)
#   3. tamper with one event's hmac
#   4. verify_chain() -> (False, <bad event id>)
