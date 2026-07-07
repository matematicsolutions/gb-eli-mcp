"""Offline unit tests for GOV.UK Search/Content API parsing helpers - no network."""

from __future__ import annotations

import json

import pytest

from gb_eli_mcp.citations import (
    human_readable_govuk_citation,
    parse_govuk_content_json,
    parse_govuk_search_json,
)

# Trimmed from a live response, 2026-07-07:
# https://www.gov.uk/api/search.json?filter_content_store_document_type=employment_tribunal_decision&count=1
SAMPLE_SEARCH = json.dumps(
    {
        "total": 132162,
        "start": 0,
        "results": [
            {
                "title": "Mr B King v Thales DIS UK Ltd: 1403603/2020",
                "description": "Employment Tribunal decision.",
                "link": (
                    "/employment-tribunal-decisions/"
                    "mr-b-king-v-thales-dis-uk-ltd-1403603-slash-2020"
                ),
                "content_store_document_type": "employment_tribunal_decision",
                "public_timestamp": "2026-07-01T13:55:40Z",
                "organisations": [
                    {"title": "HM Courts & Tribunals Service", "acronym": "HMCTS"},
                ],
            }
        ],
    }
)

# Trimmed from a live response, 2026-07-07:
# https://www.gov.uk/api/content/employment-tribunal-decisions/mr-b-king-v-thales-dis-uk-ltd-1403603-slash-2020
SAMPLE_CONTENT_TRIBUNAL = json.dumps(
    {
        "title": "Mr B King v Thales DIS UK Ltd: 1403603/2020",
        "document_type": "employment_tribunal_decision",
        "base_path": (
            "/employment-tribunal-decisions/mr-b-king-v-thales-dis-uk-ltd-1403603-slash-2020"
        ),
        "first_published_at": "2021-10-12T10:33:55+01:00",
        "public_updated_at": "2026-06-27T15:10:07+01:00",
        "details": {
            "body": '<p>Read the full decision in <a href="...">the judgment</a>.</p>',
            "attachments": [
                {
                    "title": "Judgment",
                    "url": (
                        "https://assets.publishing.service.gov.uk/media/"
                        "61654c63d3bf7f56020e4e53/Judgment.pdf"
                    ),
                    "content_type": "application/pdf",
                }
            ],
            "metadata": {"tribunal_decision_country": "England and Wales"},
        },
    }
)

# HMRC manual sections hold the body as a list of {content_type, content} parts.
SAMPLE_CONTENT_MANUAL = json.dumps(
    {
        "title": "VATGPB9700 - example section",
        "document_type": "hmrc_manual_section",
        "base_path": "/hmrc-internal-manuals/vat-government-and-public-bodies/vatgpb9700",
        "details": {
            "body": [
                {"content_type": "text/govspeak", "content": "raw govspeak"},
                {"content_type": "text/html", "content": "<p>Manual section full text.</p>"},
            ]
        },
    }
)


def test_parse_search_total_is_dedicated_field() -> None:
    total, items = parse_govuk_search_json(SAMPLE_SEARCH)
    assert total == 132162
    assert len(items) == 1


def test_parse_search_item_fields() -> None:
    _total, items = parse_govuk_search_json(SAMPLE_SEARCH)
    item = items[0]
    assert item["title"].startswith("Mr B King")
    assert item["document_type"] == "employment_tribunal_decision"
    assert item["link"].startswith("/employment-tribunal-decisions/")
    assert item["source_url"] == "https://www.gov.uk" + item["link"]
    assert item["organisations"] == ["HM Courts & Tribunals Service"]


def test_parse_search_rejects_garbage() -> None:
    with pytest.raises(ValueError, match=r"Could not parse GOV\.UK"):
        parse_govuk_search_json("not json at all")
    with pytest.raises(ValueError, match="no 'results'"):
        parse_govuk_search_json('{"nothing": true}')


def test_parse_content_tribunal_decision() -> None:
    parsed = parse_govuk_content_json(SAMPLE_CONTENT_TRIBUNAL)
    assert parsed["title"].startswith("Mr B King")
    assert parsed["document_type"] == "employment_tribunal_decision"
    assert parsed["body_html"].startswith("<p>Read the full decision")
    assert len(parsed["attachments"]) == 1
    assert parsed["attachments"][0]["content_type"] == "application/pdf"
    assert parsed["source_url"].startswith("https://www.gov.uk/employment-tribunal-decisions/")
    assert parsed["tribunal_decision_country"] == "England and Wales"


def test_parse_content_manual_body_list() -> None:
    parsed = parse_govuk_content_json(SAMPLE_CONTENT_MANUAL)
    assert parsed["body_html"] == "<p>Manual section full text.</p>"
    assert parsed["document_type"] == "hmrc_manual_section"


def test_parse_content_rejects_garbage() -> None:
    with pytest.raises(ValueError, match=r"Could not parse GOV\.UK"):
        parse_govuk_content_json("<html>not json</html>")


def test_human_readable_govuk_citation_full() -> None:
    cite = human_readable_govuk_citation(
        "Mr B King v Thales DIS UK Ltd: 1403603/2020",
        "employment_tribunal_decision",
        "2026-07-01T13:55:40Z",
    )
    assert cite == (
        "Mr B King v Thales DIS UK Ltd: 1403603/2020 "
        "(employment tribunal decision, 2026-07-01, GOV.UK)"
    )


def test_human_readable_govuk_citation_degrades() -> None:
    assert human_readable_govuk_citation(None, None, None) == "Untitled GOV.UK document (GOV.UK)"
    assert human_readable_govuk_citation("Title", None, None) == "Title (GOV.UK)"
