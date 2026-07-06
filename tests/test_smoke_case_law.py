"""Smoke tests for Find Case Law tools - require internet, not run in offline CI.

Run manually:

    pytest tests/test_smoke_case_law.py -v

All tests go through the live caselaw.nationalarchives.gov.uk site - same deliberate
POC choice as tests/test_smoke.py for legislation.gov.uk. Snapshot testing arrives in
v1.0 (TODO, tracked alongside the legislation.gov.uk TODO).
"""

from __future__ import annotations

import pytest

from gb_eli_mcp.server import gb_get_case, gb_search_case_law

# A stable, well-known neutral citation confirmed live during discovery (2026-07-06).
KNOWN_CASE = "[2026] EWHC 1658 (Admin)"


@pytest.mark.asyncio
async def test_smoke_search_case_law_by_court() -> None:
    result = await gb_search_case_law(court="ewhc/admin", limit=5)
    assert result.total_estimate > 0, "Expected hits for court=ewhc/admin"
    assert len(result.items) > 0
    for item in result.items:
        assert item.human_readable_citation is not None, f"missing citation in {item}"


@pytest.mark.asyncio
async def test_smoke_search_case_law_by_query() -> None:
    result = await gb_search_case_law(query="data protection", limit=5)
    assert result.total_estimate > 0, "Expected hits for 'data protection'"
    assert len(result.items) > 0
    for item in result.items:
        assert item.title is not None or item.neutral_citation is not None


@pytest.mark.asyncio
async def test_smoke_search_case_law_limit_respected() -> None:
    result = await gb_search_case_law(court="ewhc/admin", limit=3)
    assert len(result.items) <= 3


@pytest.mark.asyncio
async def test_smoke_search_case_law_date_range() -> None:
    result = await gb_search_case_law(
        query="negligence", from_date="2020-01-01", to_date="2020-12-31", limit=20
    )
    for item in result.items:
        if item.date:
            assert "2020-01-01" <= item.date <= "2020-12-31", f"date out of range: {item.date!r}"


@pytest.mark.asyncio
async def test_smoke_get_case_by_neutral_citation() -> None:
    case = await gb_get_case(KNOWN_CASE)
    assert case.content is not None and len(case.content) > 0
    assert "akomaNtoso" in case.content or "akn" in case.content.lower()
    assert case.neutral_citation is not None
    assert "1658" in case.neutral_citation
    assert case.source_url.startswith("https://caselaw.nationalarchives.gov.uk/")
    assert case.human_readable_citation is not None


@pytest.mark.asyncio
async def test_smoke_get_case_by_path() -> None:
    case = await gb_get_case("ewhc/admin/2026/1658")
    assert case.content is not None and len(case.content) > 0
    assert case.source_url == "https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658"
