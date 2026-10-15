"""Shared async HTTP client with polite per-host throttling."""
from __future__ import annotations

import asyncio
import time

import httpx

from ..config import get_settings


class UpstreamError(Exception):
    """An external API failed or is unreachable. The UI shows this instead of falling back to fake data."""

    def __init__(self, service: str, detail: str):
        super().__init__(f"{service}: {detail}")
        self.service = service
        self.detail = detail


class ThrottledClient:
    def __init__(self, service: str, base_url: str, min_interval_s: float = 0.0, headers: dict | None = None):
        s = get_settings()
        ua = s.user_agent + (f" mailto:{s.contact_email}" if s.contact_email else "")
        self.service = service
        self.base_url = base_url.rstrip("/")
        self.min_interval_s = min_interval_s
        self._last = 0.0
        self._lock = asyncio.Lock()
        self._headers = {"User-Agent": ua, "Accept": "application/json", **(headers or {})}
        self._timeout = s.http_timeout_s

    async def _wait(self):
        async with self._lock:
            delta = time.monotonic() - self._last
            if delta < self.min_interval_s:
                await asyncio.sleep(self.min_interval_s - delta)
            self._last = time.monotonic()

    async def request(self, method: str, path: str, *, params=None, json=None, data=None, files=None, headers=None):
        await self._wait()
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout, headers=self._headers) as client:
                r = await client.request(method, url, params=params, json=json, data=data, files=files, headers=headers)
        except httpx.HTTPError as e:
            raise UpstreamError(self.service, f"unreachable ({e.__class__.__name__}: {e})") from e
        if r.status_code == 429:
            raise UpstreamError(self.service, "rate limited (HTTP 429); retry later")
        if r.status_code >= 400:
            raise UpstreamError(self.service, f"HTTP {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else {}

    async def get(self, path: str, **params):
        clean = {k: v for k, v in params.items() if v is not None}
        return await self.request("GET", path, params=clean)
