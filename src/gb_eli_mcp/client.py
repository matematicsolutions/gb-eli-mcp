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
USER_AGENT = "gb-eli-mcp/0.3.0 (+https://github.com/matematicsolutions/gb-eli-mcp)"

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


DEFAULT_CASELAW_BASE_URL = "https://caselaw.nationalarchives.gov.uk"


class FindCaseLawClient:
    """Async client for The National Archives' Find Case Law service.

    Same conventions as ``UkLegislationClient`` (retry/backoff, disk cache, no API key -
    confirmed live 2026-07-06: every probed endpoint returns 200 with no credential).
    Kept as a separate class - different host, different Atom dialect (``tna:`` namespace).
    """

    def __init__(
        self,
        base_url: str = DEFAULT_CASELAW_BASE_URL,
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

    async def __aenter__(self) -> FindCaseLawClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

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

    async def search_feed(self, params: dict[str, Any]) -> str:
        """Fetch the Find Case Law Atom feed (``/atom.xml``).

        Confirmed live query params (from the service's own OpenAPI spec):
        ``query`` (full-text), ``court``/``tribunal`` (court code, e.g. 'ewhc/admin'),
        ``party``, ``judge``, ``order`` (default '-date'), ``page`` (default 1),
        ``per_page`` (default 50). No date-range param is documented or supported by
        the upstream API as of this probe.
        """
        clean = {k: v for k, v in params.items() if v is not None}
        return await self._get_text("/atom.xml", params=clean, category="search")

    async def get_document_xml(self, uri_path: str) -> str:
        """Fetch the Akoma Ntoso XML manifestation for a document URI path.

        ``uri_path`` is e.g. ``/ewhc/admin/2026/1658`` (pre-2025 style) or
        ``/d-f11e093f-8a53-4e43-8dd8-1531b5d8f018`` (opaque id, April 2025+).
        """
        return await self._get_text(f"{uri_path}/data.xml", category="case")

    async def get_content(self, url: str, category: str = "case") -> str:
        """Fetch an arbitrary Find Case Law URL verbatim (e.g. the PDF or HTML page)."""
        return await self._get_text(url, category=category)


DEFAULT_GOVUK_BASE_URL = "https://www.gov.uk"


class GovUkSearchClient:
    """Async client for the GOV.UK Search API + Content API.

    One upstream that aggregates MANY institutions: employment tribunal decisions,
    employment appeal tribunal decisions, tax tribunal decisions, Upper Tribunal (AAC)
    decisions, residential property tribunal decisions, HMRC internal manuals, and CMA
    competition cases all live as documents on www.gov.uk. Confirmed live 2026-07-07:
    keyless, JSON, with a dedicated ``total`` field and a
    ``facet_content_store_document_type`` facet for true per-type totals.

    Same conventions as ``UkLegislationClient`` (retry/backoff, disk cache, no API key).
    Kept as a separate class - different host, JSON instead of Atom/XML.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_GOVUK_BASE_URL,
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

    async def __aenter__(self) -> GovUkSearchClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()
        self._cache.close()

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

    async def search_json(self, params: dict[str, Any]) -> str:
        """Fetch the Search API (``/api/search.json``) as raw JSON text.

        Confirmed live query params (probed 2026-07-07):
        ``q`` (full-text), ``filter_content_store_document_type`` (e.g.
        ``employment_tribunal_decision``), ``filter_organisations`` (org slug),
        ``filter_public_timestamp=from:YYYY-MM-DD,to:YYYY-MM-DD`` (server-side date
        range), ``order`` (e.g. ``-public_timestamp``), ``count``, ``start``,
        ``fields``. The response carries a dedicated ``total`` field.
        """
        clean = {k: v for k, v in params.items() if v is not None}
        return await self._get_text("/api/search.json", params=clean, category="search")

    async def get_content_json(self, content_path: str) -> str:
        """Fetch the Content API (``/api/content/{path}``) as raw JSON text.

        ``content_path`` is the ``link`` from a search result, e.g.
        ``/employment-tribunal-decisions/mr-b-king-v-thales-dis-uk-ltd-1403603-slash-2020``
        or ``/hmrc-internal-manuals/vat-government-and-public-bodies/vatgpb9700``.
        """
        path = content_path if content_path.startswith("/") else "/" + content_path
        return await self._get_text(f"/api/content{path}", category="act")
