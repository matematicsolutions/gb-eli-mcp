"""Smoke tests - require internet, not run in offline CI.

Run manually:

    pytest tests/test_smoke.py -v

All tests go through the live legislation.gov.uk site - a deliberate POC choice.
Snapshot testing arrives in v1.0 (TODO).
"""

from __future__ import annotations

import pytest

from gb_eli_mcp.models import SearchQuery
from gb_eli_mcp.server import (
    gb_get_act,
    gb_get_text,
    gb_recent_legislation,
    gb_search,
)

# A stable, well-known UK Public General Act: Data Protection Act 2018.
DPA_2018 = "ukpga/2018/12"
# A stable UK Statutory Instrument.
UKSI_2019_419 = "uksi/2019/419"


@pytest.mark.asyncio
async def test_smoke_search_data_protection() -> None:
    result = await gb_search(SearchQuery(text="data protection", doc_type="ukpga"))
    assert result.total_estimate > 0, "Expected hits for 'data protection'"
    assert len(result.items) > 0
    # Every item must carry the contract (Art. 4 CONSTITUTION).
    for item in result.items:
        assert item.eli_uri is not None, f"missing eli_uri in {item}"
        assert item.eli_uri.startswith("https://www.legislation.gov.uk/id/"), (
            f"unexpected eli_uri: {item.eli_uri!r}"
        )
        assert item.human_readable_citation is not None, f"missing citation in {item}"
        assert item.source_url is not None, f"missing source_url in {item}"


@pytest.mark.asyncio
async def test_smoke_get_dpa_2018() -> None:
    act = await gb_get_act(DPA_2018)
    assert act.title == "Data Protection Act 2018", f"title = {act.title!r}"
    assert act.year == "2018"
    assert act.number == "12"
    assert act.human_readable_citation is not None
    assert "Data Protection Act 2018" in act.human_readable_citation
    assert "c. 12" in act.human_readable_citation
    assert act.eli_uri == "https://www.legislation.gov.uk/id/ukpga/2018/12"
    assert act.source_url == "https://www.legislation.gov.uk/ukpga/2018/12"


@pytest.mark.asyncio
async def test_smoke_get_text_xml() -> None:
    text = await gb_get_text(DPA_2018, format="xml")
    assert text.format == "xml"
    assert text.content is not None and len(text.content) > 0
    assert "legislation.gov.uk/namespaces/legislation" in text.content
    assert text.source_url.startswith("https://www.legislation.gov.uk/")
    assert text.byte_size and text.byte_size > 0


@pytest.mark.asyncio
async def test_smoke_get_text_html() -> None:
    text = await gb_get_text(DPA_2018, format="html")
    assert text.format == "html"
    assert text.content is not None and len(text.content) > 0
    assert text.source_url.startswith("https://www.legislation.gov.uk/")


@pytest.mark.asyncio
async def test_smoke_get_uksi() -> None:
    act = await gb_get_act(UKSI_2019_419)
    assert act.doc_type == "uksi"
    assert act.year == "2019"
    assert act.number == "419"
    assert act.human_readable_citation is not None
    assert "S.I. 2019/419" in act.human_readable_citation


@pytest.mark.asyncio
async def test_smoke_recent_legislation() -> None:
    items = await gb_recent_legislation(since_iso="2026-01-01", doc_type="ukpga", limit=5)
    assert len(items) > 0, "Expected at least one 2026 Public General Act"
    for item in items:
        assert item.eli_uri is not None
        assert item.human_readable_citation is not None
