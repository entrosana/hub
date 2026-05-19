"""HTTP client for CashCtrl."""

import httpx

from app.core.config import settings


class CashCtrlClient:
    def __init__(self):
        self.base = settings.cashctrl_api_base.rstrip("/")
        self.key = settings.cashctrl_api_key
        self.client = httpx.AsyncClient(timeout=15.0)

    async def _req(self, method: str, path: str, **kw):
        url = f"{self.base}/{path.lstrip('/')}"
        headers = kw.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.key}"
        r = await self.client.request(method, url, headers=headers, **kw)
        r.raise_for_status()
        return r.json()

    # ----- journals (GL entries) -----

    async def list_journals(self, *, since: str | None = None, limit: int = 100):
        return await self._req("GET", "/journal/list", params={"limit": limit, "since": since})

    async def create_journal(self, entry: dict):
        return await self._req("POST", "/journal/create", json=entry)
