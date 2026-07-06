"""FastMCP entry point - 4 super-tools for legislation.gov.uk (UK legislation).

Run:

    python -m gb_eli_mcp.server

Configuration via env:

- ``GB_ELI_CACHE_DIR`` (default ``~/.matematic/cache/gb-eli``)
- ``GB_ELI_AUDIT_DIR`` (default ``~/.matematic/audit``)
- ``GB_ELI_BASE_URL`` (default ``https://www.legislation.gov.uk``)
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .audit import AuditLogger, hash_input, timer
from .citations import (
    enrich_legislation_payload,
    parse_legislation_xml,
    parse_reference,
    parse_search_feed,
)
from .client import DEFAULT_BASE_URL, UkLegislationClient
from .models import (
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

## Hard constraints

- **UK document-type codes are the key to a reference** - a reference is `{doc_type}/{year}/{number}`, e.g. `ukpga/2018/12` (UK Public General Act), `uksi/2019/419` (UK Statutory Instrument), `asp/2015/1` (Act of the Scottish Parliament), `nia/2016/8` (Act of the Northern Ireland Assembly), `wsi/2020/1` (Wales Statutory Instrument). Do not invent a reference; get it from `gb_search` or from a response's `eli_uri`.
- **Every response has `human_readable_citation` + `source_url`** - cite both to the user (e.g. "Data Protection Act 2018 c. 12").
- **No modification of official text** - the act/instrument is returned verbatim from legislation.gov.uk.
- **Revised vs original text** - legislation.gov.uk publishes a continuously revised ("as amended") text as well as the "as enacted"/"as made" original; a response's `restrict_start_date` shows the point-in-time in force. Always relay the `dataset_note` and flag when a provision may be affected by an unapplied/pending amendment.
- **Audit log JSONL** - every tool call appends to `~/.matematic/audit/gb-eli-mcp.jsonl` (metadata + input hash only).
- **Stateless** - every call hits the upstream site; cache TTL lives client-side.

## Error iteration

Tools return a structured error with a `[code]` prefix:
- `invalid_arg` - a reference or parameter is malformed (e.g. bad `doc_type/year/number`, unsupported `format`, out-of-range `page`).
- `not_found` - the act/instrument does not exist at that reference, or the requested manifestation format is unavailable. Try `gb_search` to locate it.
- `upstream_error` - a legislation.gov.uk error (HTTP, timeout, malformed XML/Atom). Retry once before surfacing to the user.

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
    return os.environ.get("GB_ELI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


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
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the MCP server over stdio (default for Claude Code)."""
    mcp.run()


if __name__ == "__main__":
    main()
