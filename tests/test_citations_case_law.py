"""Offline unit tests for Find Case Law citation/parsing helpers - no network required."""

from __future__ import annotations

import pytest

from gb_eli_mcp.citations import (
    human_readable_case_citation,
    parse_caselaw_feed,
    parse_caselaw_uri,
    parse_neutral_citation,
)

SAMPLE_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:tna="https://caselaw.nationalarchives.gov.uk">
  <title>Latest documents</title>
  <link rel="self" href="https://caselaw.nationalarchives.gov.uk/atom.xml?page=1"/>
  <link rel="first" href="https://caselaw.nationalarchives.gov.uk/atom.xml?page=1"/>
  <link rel="last" href="https://caselaw.nationalarchives.gov.uk/atom.xml?page=7609&amp;per_page=50"/>
  <link rel="next" href="https://caselaw.nationalarchives.gov.uk/atom.xml?page=2"/>
  <entry>
    <title>Example v Another Example</title>
    <link href="https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658" rel="alternate"/>
    <published>2026-06-20T00:00:00+00:00</published>
    <updated>2026-06-21T00:00:00+00:00</updated>
    <author><name>High Court (Administrative Court)</name></author>
    <id>https://caselaw.nationalarchives.gov.uk/id/d-12345678-1234-1234-1234-123456789012</id>
    <tna:contenthash>abc123</tna:contenthash>
    <link href="https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658/data.xml" rel="alternate" type="application/akn+xml"/>
    <tna:identifier slug="ewhc/admin/2026/1658" type="ukncn">[2026] EWHC 1658 (Admin)</tna:identifier>
    <tna:identifier slug="tna.abc123" type="fclid">abc123</tna:identifier>
    <tna:uri>d-12345678-1234-1234-1234-123456789012</tna:uri>
    <link href="https://assets.caselaw.nationalarchives.gov.uk/abc/abc.pdf" rel="alternate" type="application/pdf"/>
  </entry>
</feed>
"""


def test_parse_neutral_citation_ewhc_admin() -> None:
    ncn = parse_neutral_citation("[2026] EWHC 1658 (Admin)")
    assert ncn.year == "2026"
    assert ncn.court == "ewhc"
    assert ncn.division == "admin"
    assert ncn.number == "1658"
    assert ncn.uri_path == "/ewhc/admin/2026/1658"
    assert ncn.data_xml_url == "https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658/data.xml"
    assert ncn.html_url == "https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658"


def test_parse_neutral_citation_ewca_civ() -> None:
    ncn = parse_neutral_citation("[2024] EWCA Civ 12")
    assert ncn.court == "ewca"
    assert ncn.division == "civ"
    assert ncn.number == "12"
    assert ncn.uri_path == "/ewca/civ/2024/12"


def test_parse_neutral_citation_uksc_no_division() -> None:
    ncn = parse_neutral_citation("[2023] UKSC 5")
    assert ncn.court == "uksc"
    assert ncn.division is None
    assert ncn.uri_path == "/uksc/2023/5"


def test_parse_neutral_citation_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="Not a recognisable UK neutral citation"):
        parse_neutral_citation("not a citation at all")


def test_parse_caselaw_uri_full_url() -> None:
    assert (
        parse_caselaw_uri("https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658")
        == "/ewhc/admin/2026/1658"
    )


def test_parse_caselaw_uri_bare_path() -> None:
    assert parse_caselaw_uri("ewhc/admin/2026/1658") == "/ewhc/admin/2026/1658"
    assert parse_caselaw_uri("/ewhc/admin/2026/1658") == "/ewhc/admin/2026/1658"


def test_parse_caselaw_uri_strips_data_suffix() -> None:
    assert (
        parse_caselaw_uri("https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658/data.xml")
        == "/ewhc/admin/2026/1658"
    )


def test_human_readable_case_citation() -> None:
    assert (
        human_readable_case_citation("[2026] EWHC 1658 (Admin)", "Example v Another Example")
        == "Example v Another Example [2026] EWHC 1658 (Admin)"
    )
    assert human_readable_case_citation("[2026] EWHC 1658 (Admin)", None) == "[2026] EWHC 1658 (Admin)"
    assert human_readable_case_citation(None, None) == "Unknown case"


def test_parse_caselaw_feed() -> None:
    total, items = parse_caselaw_feed(SAMPLE_FEED)
    assert total == 7609 * 50
    assert len(items) == 1
    item = items[0]
    assert item["title"] == "Example v Another Example"
    assert item["court"] == "High Court (Administrative Court)"
    assert item["date"] == "2026-06-20T00:00:00+00:00"
    assert item["neutral_citation"] == "[2026] EWHC 1658 (Admin)"
    assert item["source_url"] == "https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658"
    assert item["pdf_url"] == "https://assets.caselaw.nationalarchives.gov.uk/abc/abc.pdf"
    assert item["akn_url"] == "https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658/data.xml"


def test_parse_caselaw_feed_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="Could not parse Find Case Law Atom feed"):
        parse_caselaw_feed("not xml")
