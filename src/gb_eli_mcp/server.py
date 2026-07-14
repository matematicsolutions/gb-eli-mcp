"""FastMCP entry point - 8 tools for UK legislation, case law + GOV.UK documents.

4 tools wrap legislation.gov.uk (UK legislation); 2 wrap The National Archives' Find
Case Law service (UK case law - a separate host, added in v0.2.0); 2 wrap the GOV.UK
Search API + Content API (tribunal decisions, HMRC manuals, CMA cases - added in
v0.3.0, feature-003).

Run:

    python -m gb_eli_mcp.server

Configuration via env:

- ``GB_ELI_CACHE_DIR`` (default ``~/.matematic/cache/gb-eli``)
- ``GB_ELI_AUDIT_DIR`` (default ``~/.matematic/audit``)
- ``GB_ELI_BASE_URL`` (default ``https://www.legislation.gov.uk``)
- ``GB_ELI_CASELAW_BASE_URL`` (default ``https://caselaw.nationalarchives.gov.uk``)
- ``GB_ELI_GOVUK_BASE_URL`` (default ``https://www.gov.uk``)
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from . import runtime
from .audit import AuditLogger, hash_input, timer
from .citations import (
    enrich_legislation_payload,
    human_readable_case_citation,
    human_readable_govuk_citation,
    parse_caselaw_feed,
    parse_caselaw_uri,
    parse_govuk_content_json,
    parse_govuk_search_json,
    parse_legislation_xml,
    parse_neutral_citation,
    parse_reference,
    parse_search_feed,
)
from .client import (
    DEFAULT_BASE_URL,
    FindCaseLawClient,
    GovUkSearchClient,
    UkLegislationClient,
)
from .models import (
    CaseLawDocument,
    CaseLawInfo,
    CaseLawSearchQuery,
    CaseLawSearchResult,
    GovUkContent,
    GovUkDocumentInfo,
    GovUkSearchQuery,
    GovUkSearchResult,
    Legislation,
    LegislationInfo,
    LegislationText,
    RecentChangeInfo,
    SearchQuery,
    SearchResult,
    TextFormat,
)

# ---------------------------------------------------------------------------
# Instructions (procedural orchestration) - injected into the MCP client's
# system prompt. The LLM sees this BEFORE the first tool call.
# The drift test (tests/test_instructions_drift.py) fails if a tool in
# INSTRUCTIONS is not registered or an ErrorCode is undocumented.
# Pattern from dograh-hq/dograh v1.31.0 (BSD-2) via mcp-eu-compliance v0.2.0.
# ---------------------------------------------------------------------------

INSTRUCTIONS = """\
This MCP server exposes legislation.gov.uk, The National Archives' official portal for United Kingdom legislation - Acts of Parliament, Statutory Instruments, and the equivalent instruments of the Scottish Parliament, Senedd Cymru/Welsh Parliament and Northern Ireland Assembly. Every response carries a stable `eli_uri`, a `human_readable_citation` and a `source_url` (the citation contract). legislation.gov.uk has NO native `/eli/` namespace (confirmed live), so `eli_uri` carries the UK's own persistent identifier URI instead of a fabricated ELI - see the `dataset_note` on every response.

## Call order

### A concrete act or instrument
1. `gb_get_act` - if you know the reference (e.g. `ukpga/2018/12` for the Data Protection Act 2018, or a full legislation.gov.uk URL). Fastest. Returns metadata.
2. `gb_get_text` - full text in `xml`, `html`, `akn` (Akoma Ntoso), `rdf`, `pdf`, or `csv`. Fetches the manifestation for the given reference and format.

### Searching by metadata
3. `gb_search` - full-text/title search via the official Atom search feed. Filter by `doc_type` (e.g. `ukpga`, `uksi`, `asp`, `nia`, `wsi`) and/or `year`; paginate with `page`.

### Monitoring changes
4. `gb_recent_legislation` - legislation published since `since_iso` (ISO 8601), newest-first, optionally filtered by `doc_type`. Useful for a law-monitoring feature.

### Case law (The National Archives' Find Case Law - a separate service, separate host)
5. `gb_search_case_law` - full-text search of UK judgments via the public Find Case Law Atom feed (`caselaw.nationalarchives.gov.uk/atom.xml`). Filter by `court` (e.g. `ewhc/admin`, `ewca/civ`, `uksc`), `from_date`/`to_date` (applied client-side - see Hard constraints), paginate with `limit`.
6. `gb_get_case` - fetch a judgment by neutral citation (e.g. `"[2026] EWHC 1698 (Admin)"`) or a Find Case Law URI/path. Returns Akoma Ntoso XML content when derivable, else the PDF link.

### GOV.UK documents (tribunal decisions, HMRC manuals, CMA cases - www.gov.uk, a third host)
7. `gb_search_govuk` - full-text search of GOV.UK via its Search API (`/api/search.json`, keyless). Filter by `document_type` - the legally weighty ones with live-verified totals (2026-07-07): `employment_tribunal_decision` (132,162), `hmrc_manual_section` (85,315), `residential_property_tribunal_decision` (17,088), `employment_appeal_tribunal_decision` (2,571), `cma_case` (2,565), `utaac_decision` (2,031), `tax_tribunal_decision` (1,414), `asylum_support_decision` (101). Also `organisation`, `from_date`/`to_date` (server-side, unlike Find Case Law), `limit`, `start`.
8. `gb_get_govuk_content` - fetch one GOV.UK document by its `link` path via the Content API (`/api/content/{path}`). Tribunal decisions return metadata + the judgment PDF in `attachments`; HMRC manual sections return the full text in `body_html`.

## Hard constraints

- **UK document-type codes are the key to a reference** - a reference is `{doc_type}/{year}/{number}`, e.g. `ukpga/2018/12` (UK Public General Act), `uksi/2019/419` (UK Statutory Instrument), `asp/2015/1` (Act of the Scottish Parliament), `nia/2016/8` (Act of the Northern Ireland Assembly), `wsi/2020/1` (Wales Statutory Instrument). Do not invent a reference; get it from `gb_search` or from a response's `eli_uri`.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user (e.g. "Data Protection Act 2018 c. 12").
- **No modification of official text** - the act/instrument is returned verbatim from legislation.gov.uk.
- **Revised vs original text** - legislation.gov.uk publishes a continuously revised ("as amended") text as well as the "as enacted"/"as made" original; a response's `restrict_start_date` shows the point-in-time in force. Always relay the `dataset_note` and flag when a provision may be affected by an unapplied/pending amendment.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/gb-eli-mcp.jsonl` (metadata + input hash only).
- **Stateless** - every call hits the upstream site; cache TTL lives client-side.
- **Find Case Law has no documented date-range filter** - `gb_search_case_law`'s `from_date`/`to_date` are applied client-side against each result's `date` field after fetching, not passed upstream as query params (confirmed against the service's own OpenAPI spec, 2026-07-06).
- **Neutral citation URI derivation is best-effort** - `gb_get_case` can build a Find Case Law URI directly from a pre-April-2025-style neutral citation (`/{court}/{year}/{number}`), but documents published from April 2025 onward use an opaque `d-{uuid}` id that cannot be derived from the citation alone; those require `gb_search_case_law` first to resolve the id.
- **GOV.UK documents have no neutral citation or ELI** - `gb_search_govuk`/`gb_get_govuk_content` responses carry `human_readable_citation` as "{Title} ({document type}, {date}, GOV.UK)" plus `source_url`; a GOV.UK tribunal decision's authoritative text is the judgment PDF in `attachments`, NOT the short HTML body. Do not present the HTML body of a tribunal decision as the full judgment.
- **GOV.UK search totals are real** - `gb_search_govuk`'s `total` is the Search API's own dedicated total field (verified live against the per-type facet counts, 2026-07-07), not a page-count estimate.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a reference or parameter is malformed (e.g. bad `doc_type/year/number`, unsupported `format`, out-of-range `page`, unparseable neutral citation).
- `not_found` - the act/instrument/case does not exist at that reference, or the requested manifestation format is unavailable. Try `gb_search`/`gb_search_case_law` to locate it.
- `upstream_error` - a legislation.gov.uk, Find Case Law or GOV.UK error (HTTP, timeout, malformed XML/Atom/JSON). Retry once before surfacing to the user.

## Response style

- Cite items in `human_readable_citation` form with the reference: "Data Protection Act 2018 c. 12, ukpga/2018/12".
- NEVER invent a reference, citation, or date - take each from `eli_uri` / `source_url` / the parsed metadata.
- Always relay the `dataset_note` when the amendment/consolidation state matters to the answer.
"""


class GbEliError(Exception):
    """Structured error for gb-eli MCP tools - visible to the LLM with a [code] prefix."""

    VALID_CODES = frozenset({
        "invalid_arg",
        "not_found",
        "upstream_error",
    })

    def __init__(self, code: str, message: str):
        if code not in self.VALID_CODES:
            raise ValueError(f"Unknown GbEliError code: {code}. Valid: {sorted(self.VALID_CODES)}")
        self.code = code
        super().__init__(f"[{code}] {message}")


READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    idempotentHint=True,
    destructiveHint=False,
    openWorldHint=True,  # upstream legislation.gov.uk live
)

_ALLOWED_TEXT_FORMATS = frozenset({"xml", "html", "akn", "rdf", "pdf", "csv"})

mcp: FastMCP = FastMCP(name="gb-eli-mcp", instructions=INSTRUCTIONS)


def _base_url() -> str:
    return os.environ.get("GB_ELI_BASE_URL", runtime.base_url("eli", DEFAULT_BASE_URL)).rstrip("/")


def _caselaw_base_url() -> str:
    from .client import DEFAULT_CASELAW_BASE_URL

    return os.environ.get("GB_ELI_CASELAW_BASE_URL", runtime.base_url("eli_caselaw", DEFAULT_CASELAW_BASE_URL)).rstrip("/")


def _govuk_base_url() -> str:
    from .client import DEFAULT_GOVUK_BASE_URL

    return os.environ.get("GB_ELI_GOVUK_BASE_URL", runtime.base_url("eli_govuk", DEFAULT_GOVUK_BASE_URL)).rstrip("/")


def _audit() -> AuditLogger:
    return AuditLogger()


def _map_http_error(exc: Exception) -> Exception:
    """Translate an httpx 404 into a structured not_found; otherwise upstream_error."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return GbEliError(
            "not_found", "Legislation not found at that reference. Try gb_search to locate it."
        )
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return GbEliError("upstream_error", f"legislation.gov.uk error: {type(exc).__name__}: {exc}")
    return exc


def _map_caselaw_http_error(exc: Exception) -> Exception:
    """Translate an httpx 404 into a structured not_found; otherwise upstream_error."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return GbEliError(
            "not_found",
            "Case not found at that reference. Try gb_search_case_law to locate it.",
        )
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return GbEliError(
            "upstream_error", f"caselaw.nationalarchives.gov.uk error: {type(exc).__name__}: {exc}"
        )
    return exc


def _map_govuk_http_error(exc: Exception) -> Exception:
    """Translate an httpx 404 into a structured not_found; otherwise upstream_error."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return GbEliError(
            "not_found",
            "GOV.UK document not found at that path. Try gb_search_govuk to locate it.",
        )
    if isinstance(exc, (httpx.HTTPStatusError, httpx.TransportError, httpx.TimeoutException)):
        return GbEliError("upstream_error", f"www.gov.uk error: {type(exc).__name__}: {exc}")
    return exc


# ---------------------------------------------------------------------------
# gb_search
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def gb_search(query: SearchQuery) -> SearchResult:
    """Search UK legislation on legislation.gov.uk.

    Maps to the official Atom search feed (``/all/data.feed`` or ``/{doc_type}/data.feed``,
    optionally with ``?text=...&year=...&page=...``). Each item gets ``eli_uri``,
    ``human_readable_citation``, ``source_url`` (per Art. 4 CONSTITUTION).

    Args:
        query: ``SearchQuery`` - text, doc_type (e.g. 'ukpga', 'uksi', 'asp'), year, page.

    Returns:
        ``SearchResult`` with ``total_estimate`` and ``items: list[LegislationInfo]``.
    """
    audit = _audit()
    input_hash = hash_input(query.model_dump(mode="json"))
    base = _base_url()

    if query.page < 1:
        raise GbEliError("invalid_arg", f"page={query.page} must be >= 1.")

    params: dict[str, Any] = {
        "text": query.text,
        "year": query.year,
        "page": query.page if query.page > 1 else None,
        "doc_type": query.doc_type,
    }

    with timer() as t:
        try:
            async with UkLegislationClient(base_url=base) as client:
                raw = await client.search_feed(dict(params))
        except Exception as exc:
            audit.log(
                tool="gb_search",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    try:
        total, items_raw = parse_search_feed(raw)
    except ValueError as exc:
        audit.log(
            tool="gb_search",
            input_hash=input_hash,
            output_count_or_size=0,
            duration_ms=t.duration_ms,
            status="error",
            error=str(exc),
        )
        raise GbEliError("upstream_error", str(exc)) from exc

    items: list[LegislationInfo] = []
    for raw_item in items_raw:
        id_uri = raw_item.get("id_uri")
        if id_uri:
            try:
                ref = parse_reference(id_uri)
                enriched = enrich_legislation_payload(raw_item, ref)
                items.append(LegislationInfo.model_validate(enriched))
                continue
            except ValueError:
                pass
        # Fall back: no parseable reference, surface raw metadata without the contract.
        items.append(LegislationInfo.model_validate(raw_item))

    result = SearchResult(total_estimate=total, items=items, query_echo=query)

    audit.log(
        tool="gb_search",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# gb_get_act
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def gb_get_act(reference: str) -> Legislation:
    """Fetch UK legislation metadata from legislation.gov.uk by reference.

    Args:
        reference: a reference like ``"ukpga/2018/12"`` (Data Protection Act 2018),
            ``"uksi/2019/419"``, ``"asp/2015/1"``, or a full legislation.gov.uk URL.
            An optional point-in-time date suffix (``/2026-06-19``) selects a specific
            revised version.

    Returns:
        ``Legislation`` with ``eli_uri``, ``human_readable_citation``, ``source_url``.
    """
    audit = _audit()
    input_hash = hash_input({"reference": reference})
    base = _base_url()

    try:
        ref = parse_reference(reference)
    except ValueError as exc:
        raise GbEliError("invalid_arg", str(exc)) from exc

    with timer() as t:
        try:
            async with UkLegislationClient(base_url=base) as client:
                raw_xml = await client.get_data_xml(ref.work_path if not ref.point_in_time
                                                     else f"{ref.work_path}/{ref.point_in_time}")
        except Exception as exc:
            audit.log(
                tool="gb_get_act",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    try:
        parsed = parse_legislation_xml(raw_xml)
    except ValueError as exc:
        audit.log(
            tool="gb_get_act",
            input_hash=input_hash,
            output_count_or_size=0,
            duration_ms=t.duration_ms,
            status="error",
            error=str(exc),
        )
        raise GbEliError("upstream_error", str(exc)) from exc

    parsed["doc_type"] = ref.doc_type
    parsed.setdefault("year", ref.year)
    parsed.setdefault("number", ref.number)
    enriched = enrich_legislation_payload(parsed, ref)
    act = Legislation.model_validate(enriched)

    audit.log(
        tool="gb_get_act",
        input_hash=input_hash,
        output_count_or_size=1,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return act


# ---------------------------------------------------------------------------
# gb_get_text
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def gb_get_text(reference: str, format: TextFormat = "html") -> LegislationText:
    """Fetch the full text of UK legislation.

    Uses legislation.gov.uk's content-negotiation path suffix (``/data.{format}``) -
    ``xml`` (the site's own ``legislation.xsd`` schema), ``html``, ``akn`` (Akoma Ntoso),
    ``rdf``, ``pdf``, or ``csv``.

    Args:
        reference: reference of the act/instrument (work or point-in-time expression).
        format: one of ``"xml"``, ``"html"``, ``"akn"``, ``"rdf"``, ``"pdf"``, ``"csv"``.

    Returns:
        ``LegislationText`` with ``eli_uri``, ``human_readable_citation``, ``source_url``,
        ``content``.
    """
    audit = _audit()
    input_hash = hash_input({"reference": reference, "format": format})
    base = _base_url()

    if format not in _ALLOWED_TEXT_FORMATS:
        raise GbEliError(
            "invalid_arg",
            f"Unsupported format: {format!r}. Allowed: {sorted(_ALLOWED_TEXT_FORMATS)}.",
        )

    try:
        ref = parse_reference(reference)
    except ValueError as exc:
        raise GbEliError("invalid_arg", str(exc)) from exc

    work_path = ref.work_path if not ref.point_in_time else f"{ref.work_path}/{ref.point_in_time}"
    data_url = f"{base}{work_path}/data.{format}"

    with timer() as t:
        try:
            async with UkLegislationClient(base_url=base) as client:
                text = await client.get_content(data_url)
                # For metadata (citation), we also need the parsed XML unless we
                # already fetched it as this format.
                if format == "xml":
                    parsed = parse_legislation_xml(text)
                else:
                    xml_text = await client.get_data_xml(work_path)
                    parsed = parse_legislation_xml(xml_text)
        except GbEliError:
            audit.log(
                tool="gb_get_text",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
            )
            raise
        except Exception as exc:
            audit.log(
                tool="gb_get_text",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    parsed["doc_type"] = ref.doc_type
    parsed.setdefault("year", ref.year)
    parsed.setdefault("number", ref.number)
    enriched = enrich_legislation_payload(parsed, ref)

    result = LegislationText(
        eli_uri=enriched.get("eli_uri", ref.id_uri),
        human_readable_citation=enriched.get("human_readable_citation"),
        source_url=data_url,
        format=format,
        content=text,
        byte_size=len(text.encode("utf-8")),
    )

    audit.log(
        tool="gb_get_text",
        input_hash=input_hash,
        output_count_or_size=result.byte_size or 0,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# gb_recent_legislation
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def gb_recent_legislation(
    since_iso: str, doc_type: str | None = None, limit: int = 20
) -> list[RecentChangeInfo]:
    """UK legislation published since ``since_iso`` (ISO 8601 date), newest-first.

    Maps to the Atom search feed sorted/filtered by publication year, optionally scoped
    to one ``doc_type``. legislation.gov.uk's public search feed does not support a
    generic ``dateFrom`` filter across all types, so this tool filters the requested
    year's feed by the ``published`` date client-side.

    Args:
        since_iso: a date in ISO 8601 (e.g. ``"2026-01-01"``). Only the year is used to
            select the feed to scan; items are then filtered to on/after this date.
        doc_type: restrict to one UK document-type code (e.g. ``"ukpga"``, ``"uksi"``).
        limit: max items to return (1..100).

    Returns:
        List of ``RecentChangeInfo`` enriched with the citation contract, newest-first.
    """
    audit = _audit()
    input_hash = hash_input({"since": since_iso, "doc_type": doc_type, "limit": limit})
    base = _base_url()

    if not 1 <= limit <= 100:
        raise GbEliError("invalid_arg", f"limit={limit} out of range 1..100.")
    if len(since_iso) < 10 or since_iso[4] != "-" or since_iso[7] != "-":
        raise GbEliError("invalid_arg", f"since_iso={since_iso!r} must be ISO 8601 (YYYY-MM-DD).")

    year = int(since_iso[:4])
    params: dict[str, Any] = {"year": year, "doc_type": doc_type}

    with timer() as t:
        try:
            async with UkLegislationClient(base_url=base) as client:
                raw = await client.search_feed(dict(params))
        except Exception as exc:
            audit.log(
                tool="gb_recent_legislation",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_http_error(exc) from exc

    try:
        _total, items_raw = parse_search_feed(raw)
    except ValueError as exc:
        audit.log(
            tool="gb_recent_legislation",
            input_hash=input_hash,
            output_count_or_size=0,
            duration_ms=t.duration_ms,
            status="error",
            error=str(exc),
        )
        raise GbEliError("upstream_error", str(exc)) from exc

    filtered = [it for it in items_raw if (it.get("published") or "") >= since_iso]
    filtered.sort(key=lambda it: it.get("published") or "", reverse=True)

    items: list[RecentChangeInfo] = []
    for raw_item in filtered[:limit]:
        id_uri = raw_item.get("id_uri")
        if id_uri:
            try:
                ref = parse_reference(id_uri)
                enriched = enrich_legislation_payload(raw_item, ref)
                items.append(RecentChangeInfo.model_validate(enriched))
                continue
            except ValueError:
                pass
        items.append(RecentChangeInfo.model_validate(raw_item))

    audit.log(
        tool="gb_recent_legislation",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return items


# ---------------------------------------------------------------------------
# gb_search_case_law
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def gb_search_case_law(
    query: str | None = None,
    court: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 20,
) -> CaseLawSearchResult:
    """Search UK case law on The National Archives' Find Case Law service.

    Maps to the public Atom feed at ``caselaw.nationalarchives.gov.uk/atom.xml``
    (confirmed live 2026-07-06 - keyless, Open Justice Licence). A separate service from
    legislation.gov.uk: different host, different Atom dialect (``tna:`` namespace).

    Args:
        query: full-text search (matches judgment text in order, per upstream docs).
        court: court/tribunal code, e.g. ``"ewhc/admin"``, ``"ewca/civ"``, ``"uksc"``.
            Passed through to Find Case Law's own ``court`` query param.
        from_date: ISO 8601 date (YYYY-MM-DD), inclusive. Find Case Law's public API has
            no documented server-side date-range filter, so this is applied client-side
            against each result's ``date`` field after fetching.
        to_date: ISO 8601 date (YYYY-MM-DD), inclusive. Same client-side caveat.
        limit: max items to return (1..100).

    Returns:
        ``CaseLawSearchResult`` with ``total_estimate`` and ``items: list[CaseLawInfo]``.
    """
    audit = _audit()
    input_hash = hash_input(
        {"query": query, "court": court, "from_date": from_date, "to_date": to_date, "limit": limit}
    )
    base = _caselaw_base_url()

    if not 1 <= limit <= 100:
        raise GbEliError("invalid_arg", f"limit={limit} out of range 1..100.")
    for label, value in (("from_date", from_date), ("to_date", to_date)):
        if value is not None and (len(value) < 10 or value[4] != "-" or value[7] != "-"):
            raise GbEliError("invalid_arg", f"{label}={value!r} must be ISO 8601 (YYYY-MM-DD).")

    params: dict[str, Any] = {
        "query": query,
        "court": court,
        "per_page": min(limit, 50),
    }

    with timer() as t:
        try:
            async with FindCaseLawClient(base_url=base) as client:
                raw = await client.search_feed(dict(params))
        except Exception as exc:
            audit.log(
                tool="gb_search_case_law",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_caselaw_http_error(exc) from exc

    try:
        total, items_raw = parse_caselaw_feed(raw)
    except ValueError as exc:
        audit.log(
            tool="gb_search_case_law",
            input_hash=input_hash,
            output_count_or_size=0,
            duration_ms=t.duration_ms,
            status="error",
            error=str(exc),
        )
        raise GbEliError("upstream_error", str(exc)) from exc

    if from_date is not None:
        items_raw = [it for it in items_raw if (it.get("date") or "") >= from_date]
    if to_date is not None:
        items_raw = [it for it in items_raw if (it.get("date") or "9999-99-99") <= to_date]

    items: list[CaseLawInfo] = []
    for raw_item in items_raw[:limit]:
        enriched = dict(raw_item)
        enriched["human_readable_citation"] = human_readable_case_citation(
            raw_item.get("neutral_citation"), raw_item.get("title")
        )
        items.append(CaseLawInfo.model_validate(enriched))

    result = CaseLawSearchResult(
        total_estimate=total,
        items=items,
        query_echo=CaseLawSearchQuery(
            query=query, court=court, from_date=from_date, to_date=to_date, limit=limit
        ),
    )

    audit.log(
        tool="gb_search_case_law",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# gb_get_case
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def gb_get_case(reference: str) -> CaseLawDocument:
    """Fetch a UK judgment from The National Archives' Find Case Law service.

    Args:
        reference: a neutral citation (e.g. ``"[2026] EWHC 1698 (Admin)"``), a Find Case
            Law URI/path (e.g. ``"ewhc/admin/2026/1698"`` or a full
            ``caselaw.nationalarchives.gov.uk`` URL), or an opaque ``"d-{uuid}"`` id.
            Neutral citations resolve directly to a URI only for pre-April-2025 documents
            (``/{court}/{year}/{number}``); for later documents (opaque id), use
            `gb_search_case_law` first to find the ``uri``.

    Returns:
        ``CaseLawDocument`` with ``human_readable_citation``, ``source_url``, and the
        Akoma Ntoso XML ``content`` (or a ``pdf_url`` fallback if XML is unavailable).
    """
    audit = _audit()
    input_hash = hash_input({"reference": reference})
    base = _caselaw_base_url()

    raw = reference.strip()
    try:
        if raw.startswith("["):
            ncn = parse_neutral_citation(raw)
            uri_path = ncn.uri_path
            neutral_citation = ncn.raw
        else:
            uri_path = parse_caselaw_uri(raw)
            neutral_citation = None
    except ValueError as exc:
        raise GbEliError("invalid_arg", str(exc)) from exc

    source_url = f"{base}{uri_path}"
    # PDF asset host mirrors the doc URI path as a single slug: uri_path "/ewhc/admin/2026/1698"
    # -> id "ewhc-admin-2026-1698" -> ".../{id}/{id}.pdf" (confirmed live pattern; best-effort,
    # not guaranteed for opaque "d-{uuid}" ids where the id itself already contains no slashes).
    _pdf_id = uri_path.strip("/").replace("/", "-")
    pdf_url = f"https://assets.caselaw.nationalarchives.gov.uk/{_pdf_id}/{_pdf_id}.pdf"

    xml_text: str | None = None
    akn_error: Exception | None = None
    with timer() as t:
        try:
            async with FindCaseLawClient(base_url=base) as client:
                xml_text = await client.get_document_xml(uri_path)
        except Exception as exc:
            akn_error = exc

        if xml_text is None:
            # AKN+XML fetch failed - fall back to the PDF link with whatever metadata we
            # already have (best-effort; we do NOT attempt to parse the PDF binary).
            mapped = _map_caselaw_http_error(akn_error) if akn_error is not None else None
            if isinstance(mapped, GbEliError) and mapped.code == "not_found":
                audit.log(
                    tool="gb_get_case",
                    input_hash=input_hash,
                    output_count_or_size=0,
                    duration_ms=t.duration_ms if t.duration_ms else 0,
                    status="error",
                    error=f"{type(akn_error).__name__}: {akn_error}" if akn_error else "not_found",
                )
                raise mapped from akn_error

            doc = CaseLawDocument(
                neutral_citation=neutral_citation,
                human_readable_citation=human_readable_case_citation(neutral_citation, None),
                source_url=source_url,
                format="pdf",
                content=None,
                pdf_url=pdf_url,
                byte_size=None,
            )
            audit.log(
                tool="gb_get_case",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="ok",
                error=(
                    f"AKN+XML unavailable, PDF-only fallback: "
                    f"{type(akn_error).__name__}: {akn_error}"
                    if akn_error
                    else None
                ),
            )
            return doc

    if neutral_citation is None:
        m = re.search(r"\[\d{4}\]\s*\w+.*?\d+\s*(?:\([\w\s]+\))?", xml_text)
        neutral_citation = m.group(0).strip() if m else None

    title_match = re.search(r"<FRBRalias[^>]*value=\"([^\"]+)\"", xml_text)
    title = title_match.group(1) if title_match else None

    doc = CaseLawDocument(
        title=title,
        neutral_citation=neutral_citation,
        human_readable_citation=human_readable_case_citation(neutral_citation, title),
        source_url=source_url,
        format="akn",
        content=xml_text,
        byte_size=len(xml_text.encode("utf-8")),
    )

    audit.log(
        tool="gb_get_case",
        input_hash=input_hash,
        output_count_or_size=doc.byte_size or 0,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return doc


# ---------------------------------------------------------------------------
# gb_search_govuk
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def gb_search_govuk(
    query: str | None = None,
    document_type: str | None = None,
    organisation: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 20,
    start: int = 0,
) -> GovUkSearchResult:
    """Search GOV.UK documents - tribunal decisions, HMRC manuals, CMA cases and more.

    Maps to the GOV.UK Search API (``www.gov.uk/api/search.json`` - confirmed live
    2026-07-07: keyless, Open Government Licence v3.0). One upstream aggregating many
    institutions; filter with ``document_type``. Legally weighty types with live-verified
    totals (2026-07-07): ``employment_tribunal_decision`` (132,162),
    ``hmrc_manual_section`` (85,315), ``residential_property_tribunal_decision``
    (17,088), ``employment_appeal_tribunal_decision`` (2,571), ``cma_case`` (2,565),
    ``utaac_decision`` (2,031), ``tax_tribunal_decision`` (1,414),
    ``asylum_support_decision`` (101).

    Args:
        query: full-text search terms.
        document_type: GOV.UK ``content_store_document_type`` slug (see above).
        organisation: GOV.UK organisation slug, e.g. ``"competition-and-markets-authority"``.
        from_date: ISO 8601 date (YYYY-MM-DD), inclusive - passed server-side via
            ``filter_public_timestamp`` (unlike Find Case Law, GOV.UK supports this).
        to_date: ISO 8601 date (YYYY-MM-DD), inclusive. Same server-side filter.
        limit: max items to return (1..100).
        start: result offset for pagination (0-based).

    Returns:
        ``GovUkSearchResult`` with the API's own ``total`` and
        ``items: list[GovUkDocumentInfo]``.
    """
    audit = _audit()
    input_hash = hash_input(
        {
            "query": query,
            "document_type": document_type,
            "organisation": organisation,
            "from_date": from_date,
            "to_date": to_date,
            "limit": limit,
            "start": start,
        }
    )
    base = _govuk_base_url()

    if not 1 <= limit <= 100:
        raise GbEliError("invalid_arg", f"limit={limit} out of range 1..100.")
    if start < 0:
        raise GbEliError("invalid_arg", f"start={start} must be >= 0.")
    for label, value in (("from_date", from_date), ("to_date", to_date)):
        if value is not None and (len(value) < 10 or value[4] != "-" or value[7] != "-"):
            raise GbEliError("invalid_arg", f"{label}={value!r} must be ISO 8601 (YYYY-MM-DD).")

    timestamp_filter: str | None = None
    if from_date or to_date:
        parts = []
        if from_date:
            parts.append(f"from:{from_date}")
        if to_date:
            parts.append(f"to:{to_date}")
        timestamp_filter = ",".join(parts)

    params: dict[str, Any] = {
        "q": query,
        "filter_content_store_document_type": document_type,
        "filter_organisations": organisation,
        "filter_public_timestamp": timestamp_filter,
        "count": limit,
        "start": start if start > 0 else None,
        "order": "-public_timestamp" if not query else None,
        "fields": "title,link,description,public_timestamp,content_store_document_type,organisations",
    }

    with timer() as t:
        try:
            async with GovUkSearchClient(base_url=base) as client:
                raw = await client.search_json(dict(params))
        except Exception as exc:
            audit.log(
                tool="gb_search_govuk",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_govuk_http_error(exc) from exc

    try:
        total, items_raw = parse_govuk_search_json(raw)
    except ValueError as exc:
        audit.log(
            tool="gb_search_govuk",
            input_hash=input_hash,
            output_count_or_size=0,
            duration_ms=t.duration_ms,
            status="error",
            error=str(exc),
        )
        raise GbEliError("upstream_error", str(exc)) from exc

    items: list[GovUkDocumentInfo] = []
    for raw_item in items_raw:
        enriched = dict(raw_item)
        enriched["human_readable_citation"] = human_readable_govuk_citation(
            raw_item.get("title"), raw_item.get("document_type"), raw_item.get("public_timestamp")
        )
        items.append(GovUkDocumentInfo.model_validate(enriched))

    result = GovUkSearchResult(
        total=total,
        items=items,
        query_echo=GovUkSearchQuery(
            query=query,
            document_type=document_type,
            organisation=organisation,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            start=start,
        ),
    )

    audit.log(
        tool="gb_search_govuk",
        input_hash=input_hash,
        output_count_or_size=len(items),
        duration_ms=t.duration_ms,
        status="ok",
    )
    return result


# ---------------------------------------------------------------------------
# gb_get_govuk_content
# ---------------------------------------------------------------------------


@mcp.tool(annotations=READ_ONLY)
async def gb_get_govuk_content(path: str) -> GovUkContent:
    """Fetch one GOV.UK document (tribunal decision, HMRC manual section, CMA case).

    Maps to the GOV.UK Content API (``www.gov.uk/api/content/{path}`` - confirmed live
    2026-07-07). Tribunal decisions carry the judgment as a PDF in ``attachments`` with
    only a short HTML body; HMRC manual sections carry the full text in ``body_html``.

    Args:
        path: the document's site path - take it from a ``gb_search_govuk`` result's
            ``link`` field, e.g.
            ``"/employment-tribunal-decisions/mr-b-king-v-thales-dis-uk-ltd-1403603-slash-2020"``
            or ``"/hmrc-internal-manuals/vat-government-and-public-bodies/vatgpb9700"``.
            A full ``www.gov.uk`` URL is also accepted.

    Returns:
        ``GovUkContent`` with ``human_readable_citation``, ``source_url``, ``body_html``
        and ``attachments``.
    """
    audit = _audit()
    input_hash = hash_input({"path": path})
    base = _govuk_base_url()

    raw_path = path.strip()
    if raw_path.startswith("http://") or raw_path.startswith("https://"):
        after_scheme = raw_path.split("://", 1)[1]
        raw_path = "/" + (after_scheme.split("/", 1)[1] if "/" in after_scheme else "")
    if not raw_path.startswith("/"):
        raw_path = "/" + raw_path
    raw_path = raw_path.removeprefix("/api/content")
    if raw_path in ("", "/"):
        raise GbEliError("invalid_arg", f"path={path!r} is not a GOV.UK content path.")

    with timer() as t:
        try:
            async with GovUkSearchClient(base_url=base) as client:
                raw = await client.get_content_json(raw_path)
        except Exception as exc:
            audit.log(
                tool="gb_get_govuk_content",
                input_hash=input_hash,
                output_count_or_size=0,
                duration_ms=t.duration_ms if t.duration_ms else 0,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise _map_govuk_http_error(exc) from exc

    try:
        parsed = parse_govuk_content_json(raw)
    except ValueError as exc:
        audit.log(
            tool="gb_get_govuk_content",
            input_hash=input_hash,
            output_count_or_size=0,
            duration_ms=t.duration_ms,
            status="error",
            error=str(exc),
        )
        raise GbEliError("upstream_error", str(exc)) from exc

    parsed["human_readable_citation"] = human_readable_govuk_citation(
        parsed.get("title"),
        parsed.get("document_type"),
        parsed.get("first_published_at") or parsed.get("public_updated_at"),
    )
    parsed.setdefault("source_url", f"{base}{raw_path}")
    body = parsed.get("body_html")
    if isinstance(body, str):
        parsed["byte_size"] = len(body.encode("utf-8"))

    doc = GovUkContent.model_validate(parsed)

    audit.log(
        tool="gb_get_govuk_content",
        input_hash=input_hash,
        output_count_or_size=doc.byte_size or 0,
        duration_ms=t.duration_ms,
        status="ok",
    )
    return doc


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
