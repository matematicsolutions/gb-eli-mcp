"""Smoke tests for GOV.UK tools - require internet, not run in offline CI.

Run manually:

    pytest tests/test_smoke_govuk.py -v

All tests go through the live www.gov.uk Search/Content APIs - same deliberate POC
choice as tests/test_smoke.py (legislation.gov.uk) and tests/test_smoke_case_law.py.
"""

from __future__ import annotations

import pytest

from gb_eli_mcp.server import gb_get_govuk_content, gb_search_govuk

# A stable ET decision confirmed live during discovery (2026-07-07).
KNOWN_ET_PATH = "/employment-tribunal-decisions/mr-b-king-v-thales-dis-uk-ltd-1403603-slash-2020"


@pytest.mark.asyncio
async def test_smoke_search_employment_tribunal() -> None:
    result = await gb_search_govuk(document_type="employment_tribunal_decision", limit=5)
    assert result.total > 100_000, f"ET decisions total collapsed: {result.total}"
    assert len(result.items) == 5
    for item in result.items:
        assert item.human_readable_citation is not None
        assert item.source_url is not None and item.source_url.startswith("https://www.gov.uk/")


@pytest.mark.asyncio
async def test_smoke_search_hmrc_manual_sections() -> None:
    result = await gb_search_govuk(
        query="VAT", document_type="hmrc_manual_section", limit=3
    )
    assert result.total > 0
    assert len(result.items) > 0


@pytest.mark.asyncio
async def test_smoke_search_cma_cases_with_org_filter() -> None:
    result = await gb_search_govuk(
        document_type="cma_case",
        organisation="competition-and-markets-authority",
        limit=3,
    )
    assert result.total > 1_000, f"CMA cases total collapsed: {result.total}"


@pytest.mark.asyncio
async def test_smoke_search_date_range_server_side() -> None:
    result = await gb_search_govuk(
        document_type="employment_tribunal_decision",
        from_date="2026-06-01",
        to_date="2026-07-01",
        limit=20,
    )
    assert 0 < result.total < 100_000  # a month is a real subset, not the full corpus
    for item in result.items:
        if item.public_timestamp:
            assert "2026-06-01" <= item.public_timestamp[:10] <= "2026-07-01"


@pytest.mark.asyncio
async def test_smoke_get_content_tribunal_decision() -> None:
    doc = await gb_get_govuk_content(KNOWN_ET_PATH)
    assert doc.title is not None and "King" in doc.title
    assert doc.document_type == "employment_tribunal_decision"
    assert doc.source_url == f"https://www.gov.uk{KNOWN_ET_PATH}"
    assert doc.human_readable_citation is not None
    assert len(doc.attachments) >= 1, "expected the judgment PDF attachment"
    assert any(
        (a.content_type or "") == "application/pdf" and (a.url or "").startswith("https://")
        for a in doc.attachments
    )


@pytest.mark.asyncio
async def test_smoke_get_content_hmrc_manual_section_full_text() -> None:
    # Resolve a live section via search first (contents pages have empty bodies).
    result = await gb_search_govuk(
        query="input tax", document_type="hmrc_manual_section", limit=5
    )
    assert result.items, "no HMRC manual sections found"
    fetched = False
    for item in result.items:
        if not item.link:
            continue
        doc = await gb_get_govuk_content(item.link)
        if doc.body_html and len(doc.body_html) > 200:
            fetched = True
            break
    assert fetched, "no HMRC manual section with a substantive body_html found in 5 tries"


@pytest.mark.asyncio
async def test_smoke_get_content_full_url_accepted() -> None:
    doc = await gb_get_govuk_content(f"https://www.gov.uk{KNOWN_ET_PATH}")
    assert doc.source_url == f"https://www.gov.uk{KNOWN_ET_PATH}"
