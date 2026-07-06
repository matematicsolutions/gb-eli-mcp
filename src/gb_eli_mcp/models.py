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
