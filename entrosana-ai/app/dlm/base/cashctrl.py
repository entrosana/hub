"""CashCtrl sink — implements Sink for journal entries.

Requires an HTTP client with .post/.get methods (requests, httpx).
Audit fields ride along in CashCtrl custom fields (XML-encoded).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any
from xml.sax.saxutils import escape

from .core import SignedAction


class CashCtrlAPIError(Exception):
    def __init__(self, message: str, *, errors: list[dict] | None = None):
        super().__init__(message)
        self.errors = errors or []


class CashCtrlSink:
    """Posts SignedAction(kind='booking', ...) to CashCtrl journal/create."""

    REQUIRED_FIELD_VARS = {
        "dlm_fp",
        "confidence",
        "alternatives",
        "audit_run_id",
    }

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        organisation: str,
        http,
        custom_field_vars: Mapping[str, str],
        logger: logging.Logger | None = None,
    ):
        missing = self.REQUIRED_FIELD_VARS - set(custom_field_vars.keys())
        if missing:
            raise ValueError(f"custom_field_vars missing: {sorted(missing)}")
        self._base = base_url.rstrip("/")
        self._auth = (api_key, "")
        self._org = organisation
        self._http = http
        self._fields = dict(custom_field_vars)
        self._log = logger or logging.getLogger(__name__)

    def commit(self, action: SignedAction) -> str:
        if action.kind != "booking":
            raise ValueError(f"CashCtrlSink only handles 'booking', got '{action.kind}'")

        payload = dict(action.payload)
        dec = action.receipt.decision

        body = {
            "dateAdded": payload["date_added"],
            "title": payload["title"][:200],
            "debitId": int(payload["debit_account_id"]),
            "creditId": int(payload["credit_account_id"]),
            "amount": payload["amount"],
            "reference": payload.get("reference") or dec.run_id,
            "custom": self._render_custom(
                {
                    "dlm_fp": dec.dlm_fp,
                    "confidence": str(dec.confidence),
                    "alternatives": [
                        {
                            "template_id": c.template_id,
                            "bindings": dict(c.bindings),
                            "confidence": str(c.confidence),
                        }
                        for c in dec.alternatives[:10]
                    ],
                    "audit_run_id": dec.run_id,
                }
            ),
        }

        resp = self._http.post(
            f"{self._base}/api/v1/{self._org}/journal/create.json",
            data=body,
            auth=self._auth,
            timeout=30,
        )
        if resp.status_code != 200:
            raise CashCtrlAPIError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        result = resp.json()
        if not result.get("success"):
            raise CashCtrlAPIError("booking rejected", errors=result.get("errors", []))
        booking_id = result.get("insertId")
        if not isinstance(booking_id, int):
            raise CashCtrlAPIError("response missing insertId")
        self._log.info(
            "cashctrl.booking.created",
            extra={
                "cashctrl_id": booking_id,
                "run_id": dec.run_id,
                "confidence": str(dec.confidence),
            },
        )
        return str(booking_id)

    def get_chart_of_accounts(self) -> list[dict[str, Any]]:
        resp = self._http.get(
            f"{self._base}/api/v1/{self._org}/account/list.json",
            auth=self._auth,
            timeout=30,
        )
        if resp.status_code != 200:
            raise CashCtrlAPIError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        result = resp.json()
        if not result.get("success"):
            raise CashCtrlAPIError("account list rejected", errors=result.get("errors", []))
        return result["data"]

    def _render_custom(self, values: Mapping[str, Any]) -> str:
        parts = ["<values>"]
        for name, raw in values.items():
            var = self._fields[name].lstrip("$")
            serialised = (
                json.dumps(raw, separators=(",", ":"), sort_keys=True)
                if isinstance(raw, (list, dict))
                else str(raw)
            )
            parts.append(f"<{var}>{escape(serialised)}</{var}>")
        parts.append("</values>")
        return "".join(parts)
