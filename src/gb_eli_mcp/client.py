"""Async httpx client for legislation.gov.uk (The National Archives) with cache.

legislation.gov.uk serves the same URI path as HTML (for humans) or structured XML /
Atom (for machines) via content negotiation - either an ``Accept`` header or a
``/data.xml`` (single document) / ``/data.feed`` (search & listings) path suffix. We use
the explicit suffix, which is the more robust of the two (confirmed live: both work, but
the suffix survives redirects and caching proxies more reliably than an Accept header).

No API key. No documented rate limit, but we keep our own backoff + cache regardless
(same policy as every sibling connector in this factory).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import anyio
import httpx

from .cache import HttpCache

DEFAULT_BASE_URL = "https://www.legislation.gov.uk"
DEFAULT_TIMEOUT = httpx.Timeout(40.0, connect=10.0)
USER_AGENT = "gb-eli-mcp/0.1.0 (+https://github.com/matematicsolutions/gb-eli-mcp)"

_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3


class UkLegislationClient:
    """Async client. Use as ``async with UkLegislationClient() as c: ...``."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        cache: HttpCache | None = None,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._cache = cache or HttpCache()
        self._http = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        )

    async def __aenter__(self) -> UkLegislationClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

    # ----- low-level ---------------------------------------------------------

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _cache_key(self, url: str, params: dict[str, Any] | None) -> str:
        if not params:
            return url
        items = sorted((k, v) for k, v in params.items() if v is not None)
        return f"{url}?{urlencode(items, doseq=True)}"

    async def _request_with_backoff(
        self, url: str, params: dict[str, Any] | None
    ) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                resp = await self._http.get(url, params=params)
                resp.raise_for_status()
                return resp
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS - 1:
                    raise
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1:
                    raise
            await anyio.sleep(0.5 * (2**attempt))  # 0.5s, 1s
        assert last_exc is not None
        raise last_exc

    async def _get_text(
        self, path_or_url: str, *, params: dict[str, Any] | None = None, category: str
    ) -> str:
        url = path_or_url if path_or_url.startswith("http") else self._url(path_or_url)
        key = self._cache_key(url, params)
        cached = self._cache.get(key)
        if cached is not None and isinstance(cached, str):
            return cached
        resp = await self._request_with_backoff(url, params)
        text = resp.text
        self._cache.set(key, text, ttl=HttpCache.ttl_for(category))
        return text

    # ----- typed endpoints -----------------------------------------------------

    async def get_data_xml(self, work_path: str) -> str:
        """Fetch the structured-XML manifestation for a work/expression path.

        ``work_path`` is e.g. ``/ukpga/2018/12`` or ``/ukpga/2018/12/2026-06-19``.
        """
        return await self._get_text(f"{work_path}/data.xml", category="act")

    async def search_feed(self, params: dict[str, Any]) -> str:
        """Fetch the Atom search feed (``/all/data.feed`` or scoped ``/{type}/data.feed``)."""
        doc_type = params.pop("doc_type", None)
        path = f"/{doc_type}/data.feed" if doc_type else "/all/data.feed"
        clean = {k: v for k, v in params.items() if v is not None}
        return await self._get_text(path, params=clean, category="search")

    async def get_content(self, url: str, category: str = "act") -> str:
        """Fetch an arbitrary legislation.gov.uk URL verbatim (e.g. a specific manifestation)."""
        return await self._get_text(url, category=category)
