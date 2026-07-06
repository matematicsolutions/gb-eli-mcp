"""Pydantic v2 models for legislation.gov.uk + gb-eli-mcp.

Models are deliberately tolerant (``extra="allow"``) - the source's XML schema is
large and we surface only the fields the citation contract and MVP tools need. We do
not attempt to model the full legislation.gov.uk schema (``legislation.xsd``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TextFormat = Literal["xml", "html", "akn", "rdf", "pdf", "csv"]

# legislation.gov.uk's own persistent-identifier scheme predates and closely relates to
# ELI, but the site does not publish a native /eli/ namespace (probed live: GET
# /eli/ukpga/2018/12 -> 404). eli_uri therefore carries the UK's own stable id URI
# instead of a fabricated ELI path - see CONSTITUTION.md Art. 4 and citations.py.
DATASET_NOTE = (
    "legislation.gov.uk has no native /eli/ namespace; eli_uri carries the UK's own "
    "persistent identifier URI (id.../{type}/{year}/{number}) instead of a fabricated "
    "ELI path. Revised ('as amended') text reflects the effective date shown in "
    "restrict_start_date; always check for in-force / pending amendments."
)


class _Tolerant(BaseModel):
    """Base for models that accept unforeseen fields."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


# --- legislation.gov.uk primitives ------------------------------------------------


class LegislationInfo(_Tolerant):
    """Lightweight legislation record - from a search/listing item."""

    doc_type: str | None = None
    year: str | None = None
    number: str | None = None
    title: str | None = None
    description: str | None = None
    document_main_type: str | None = None
    published: str | None = None

    # Enrichments added by our server (Art. 4 CONSTITUTION).
    eli_uri: str | None = None
    human_readable_citation: str | None = None
    source_url: str | None = None


class Legislation(_Tolerant):
    """Full legislation metadata record - GET .../data.xml."""

    doc_type: str
    year: str
    number: str
    title: str | None = None
    description: str | None = None
    document_category: str | None = None
    document_main_type: str | None = None
    document_status: str | None = None
    enactment_date: str | None = None
    made_date: str | None = None
    isbn: str | None = None
    date_modified: str | None = None
    publisher: str | None = None
    restrict_extent: str | None = None
    restrict_start_date: str | None = None

    eli_uri: str
    human_readable_citation: str
    source_url: str
    dataset_note: str = DATASET_NOTE


# --- Tool I/O ----------------------------------------------------------------------


class SearchQuery(_Tolerant):
    """Arguments for the ``gb_search`` tool."""

    text: str | None = None
    doc_type: str | None = Field(
        default=None,
        description=(
            "Restrict to one UK document-type code, e.g. 'ukpga', 'uksi', 'asp', "
            "'nia', 'wsi'. Omit to search all types."
        ),
    )
    year: int | None = None
    page: int = Field(default=1, ge=1)


class SearchResult(_Tolerant):
    """Result of ``gb_search``."""

    total_estimate: int
    items: list[LegislationInfo] = Field(default_factory=list)
    query_echo: SearchQuery | None = None
    dataset_note: str = DATASET_NOTE


class LegislationText(_Tolerant):
    """Result of ``gb_get_text``."""

    eli_uri: str
    human_readable_citation: str | None = None
    source_url: str
    format: TextFormat
    content: str | None = None
    byte_size: int | None = None
    dataset_note: str = DATASET_NOTE


class RecentChangeInfo(LegislationInfo):
    """An item from ``gb_recent_legislation``."""


# --- Case law (Find Case Law - caselaw.nationalarchives.gov.uk) --------------------

CASE_LAW_DATASET_NOTE = (
    "caselaw.nationalarchives.gov.uk (Find Case Law, The National Archives) publishes "
    "judgments under the Open Justice Licence - a separate service from legislation.gov.uk "
    "(different host, no shared identifier scheme). Pre-April-2025 documents have a "
    "derivable URI ('/{court}/{year}/{number}'); documents from April 2025 onward use an "
    "opaque 'd-{uuid}' URI (fclid) that cannot be derived from the neutral citation alone. "
    "human_readable_citation is the neutral citation, e.g. '[2026] EWHC 1698 (Admin)'."
)


class CaseLawInfo(_Tolerant):
    """Lightweight case-law record - from a Find Case Law search/feed item."""

    neutral_citation: str | None = None
    court: str | None = None
    title: str | None = None
    date: str | None = None
    fclid: str | None = None  # opaque "d-{uuid}" identifier, if present
    uri: str | None = None  # the tna:uri document UUID

    # Enrichments added by our server (Art. 4 CONSTITUTION parity for case law).
    human_readable_citation: str | None = None
    source_url: str | None = None
    pdf_url: str | None = None
    akn_url: str | None = None


class CaseLawSearchQuery(_Tolerant):
    """Arguments for the ``gb_search_case_law`` tool."""

    query: str | None = None
    court: str | None = Field(
        default=None,
        description="Court code, e.g. 'ewhc/admin', 'uksc', 'ukpc'. Omit to search all courts.",
    )
    from_date: str | None = Field(
        default=None,
        description=(
            "ISO 8601 date (YYYY-MM-DD), inclusive. Find Case Law's public API has no "
            "documented server-side date-range filter, so this is applied client-side "
            "against each result's 'date' field after fetching."
        ),
    )
    to_date: str | None = Field(default=None, description="ISO 8601 date (YYYY-MM-DD), inclusive.")
    limit: int = Field(default=20, ge=1, le=100)


class CaseLawSearchResult(_Tolerant):
    """Result of ``gb_search_case_law``."""

    total_estimate: int
    items: list[CaseLawInfo] = Field(default_factory=list)
    query_echo: CaseLawSearchQuery | None = None
    dataset_note: str = CASE_LAW_DATASET_NOTE


class CaseLawDocument(_Tolerant):
    """Result of ``gb_get_case``."""

    neutral_citation: str | None = None
    court: str | None = None
    title: str | None = None
    date: str | None = None

    human_readable_citation: str
    source_url: str
    format: Literal["akn", "pdf"] = "akn"
    content: str | None = None
    pdf_url: str | None = None
    byte_size: int | None = None
    dataset_note: str = CASE_LAW_DATASET_NOTE
