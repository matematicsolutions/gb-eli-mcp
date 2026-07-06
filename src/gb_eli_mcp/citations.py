"""UK legislation.gov.uk identifier + citation helpers.

legislation.gov.uk (The National Archives) predates ELI and uses its own
persistent-identifier scheme rather than a native ``/eli/`` namespace (probed live:
``GET /eli/ukpga/2018/12`` returns 404). Like the Dutch and Swedish connectors in this
factory, ``eli_uri`` therefore carries the UK's own stable identifier - never a
fabricated ``/eli/`` path - and this file documents that choice at the point of use.

The UK's identifier is a 4-part path: ``/{type}/{year}/{number}`` where ``type`` is
one of the UK's own document-type codes across its four legislating jurisdictions:

- ``ukpga`` - UK Public General Act (England & Wales / UK-wide)
- ``uksi``  - UK Statutory Instrument (UK-wide secondary legislation)
- ``asp``   - Act of the Scottish Parliament
- ``ssi``   - Scottish Statutory Instrument
- ``nia``   - Act of the Northern Ireland Assembly
- ``nisr``  - Northern Ireland Statutory Rule
- ``anaw``  - Act of the National Assembly for Wales / Senedd Cymru
- ``wsi``   - Wales Statutory Instrument
- ``ukla``  - UK Local Act
- ``eur``   - retained/assimilated EU Regulation on legislation.gov.uk

The canonical persistent id is ``https://www.legislation.gov.uk/id/{type}/{year}/{number}``
(no point-in-time = the "as made"/work level; a dated segment such as
``/2026-06-19`` selects a specific revised version = the expression level).

Citation contract (Art. 4 CONSTITUTION):
- ``eli_uri``: the UK's own persistent id URI (``.../id/{type}/{year}/{number}[/{date}]``).
  Documented here as NOT a native ELI - see the module docstring and CONSTITUTION.md Art. 4.
- ``human_readable_citation``: UK legal citation convention, e.g.
  "Data Protection Act 2018 c. 12" for a public general act (``c.`` = chapter number),
  or "The Police Appeals Tribunals Rules 2020 (S.I. 2020/1)" for a statutory instrument.
- ``source_url``: the browsable legislation.gov.uk page for that version.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

LEG_NS = "http://www.legislation.gov.uk/namespaces/legislation"
UKM_NS = "http://www.legislation.gov.uk/namespaces/metadata"
DC_NS = "http://purl.org/dc/elements/1.1/"
ATOM_NS = "http://www.w3.org/2005/Atom"
DCT_NS = "http://purl.org/dc/terms/"

BASE_URL = "https://www.legislation.gov.uk"

# Document-type codes that are "Acts" (primary legislation) - cited with chapter/asp/
# section number rather than "S.I." / "S.R." style. Everything else is treated as a
# statutory instrument / rule for citation purposes.
_ACT_TYPES = {
    "ukpga": "c.",  # UK Public General Act -> chapter
    "ukla": "c.",  # UK Local Act -> chapter
    "asp": "asp",  # Act of the Scottish Parliament
    "nia": "c.",  # Act of the Northern Ireland Assembly
    "anaw": "anaw",  # Act of the National Assembly for Wales / Senedd Cymru
    "apni": "c.",  # Act of the Parliament of Northern Ireland (historic)
    "aosp": "asp",  # historic Acts of the Old Scottish Parliament
    "aep": "c.",  # Acts of the English Parliament (historic)
    "gbla": "c.",  # Local Acts of Great Britain (historic)
    "aip": "c.",  # Acts of the Old Irish Parliament (historic)
}

_SI_LABELS = {
    "uksi": "S.I.",
    "ssi": "S.S.I.",
    "nisr": "S.R.",
    "wsi": "S.I.",  # Wales SIs are still numbered in the UK S.I. series unless "W." suffixed
    "ukmo": "Ministerial Order",
    "ukci": "C.I.",  # Church Instrument
}

_ID_RE = re.compile(
    r"legislation\.gov\.uk/(?:id/)?(?P<type>[a-z]+)/(?P<year>\d{4})/(?P<number>[\w-]+)"
    r"(?:/(?P<date>\d{4}-\d{2}-\d{2}))?"
)


@dataclass(frozen=True)
class UkRef:
    """Structured reference to a UK legislation item on legislation.gov.uk."""

    doc_type: str  # e.g. "ukpga", "uksi", "asp"
    year: str
    number: str
    point_in_time: str | None = None  # a revised-version date, if any

    @property
    def work_path(self) -> str:
        """Path identifying the work (no point-in-time)."""
        return f"/{self.doc_type}/{self.year}/{self.number}"

    @property
    def id_uri(self) -> str:
        """The canonical persistent identifier URI (``/id/...``)."""
        suffix = f"/{self.point_in_time}" if self.point_in_time else ""
        return f"{BASE_URL}/id{self.work_path}{suffix}"

    @property
    def data_xml_url(self) -> str:
        """The structured-XML manifestation URL for this reference."""
        suffix = f"/{self.point_in_time}" if self.point_in_time else ""
        return f"{BASE_URL}{self.work_path}{suffix}/data.xml"

    @property
    def html_url(self) -> str:
        suffix = f"/{self.point_in_time}" if self.point_in_time else ""
        return f"{BASE_URL}{self.work_path}{suffix}"


def parse_reference(value: str) -> UkRef:
    """Parse a UK legislation reference from a bare path, full URL, or id URI.

    Accepts e.g. ``"ukpga/2018/12"``, ``"/ukpga/2018/12"``,
    ``"https://www.legislation.gov.uk/ukpga/2018/12"``,
    ``"https://www.legislation.gov.uk/id/ukpga/2018/12/2026-06-19"``.
    Raises ``ValueError`` on unparseable input.
    """
    raw = value.strip()
    m = _ID_RE.search(raw)
    if m is None:
        # Try a bare "type/year/number" with no host.
        parts = [p for p in raw.strip("/").split("/") if p]
        if len(parts) >= 3 and parts[1].isdigit():
            doc_type, year, number = parts[0], parts[1], parts[2]
            point_in_time = None
            if len(parts) > 3 and re.match(r"\d{4}-\d{2}-\d{2}", parts[3]):
                point_in_time = parts[3]
            return UkRef(doc_type=doc_type, year=year, number=number, point_in_time=point_in_time)
        raise ValueError(
            f"Not a recognisable UK legislation reference: {value!r}. "
            f"Expected e.g. 'ukpga/2018/12' or a legislation.gov.uk URL."
        )
    return UkRef(
        doc_type=m.group("type"),
        year=m.group("year"),
        number=m.group("number"),
        point_in_time=m.group("date"),
    )


def _q(ns: str, tag: str) -> str:
    return f"{{{ns}}}{tag}"


def human_readable_citation(doc_type: str, year: str, number: str, title: str | None) -> str:
    """UK legal citation convention.

    - Acts: "{Title} {year} c. {number}" (or "asp {number}" / "anaw {number}" for the
      devolved legislatures, which use their own chapter-letter convention).
    - Statutory instruments / rules: "{Title} (S.I. {year}/{number})" (or S.S.I./S.R.).
    """
    label = title or f"{doc_type} {year}/{number}"
    if doc_type in _ACT_TYPES:
        marker = _ACT_TYPES[doc_type]
        if marker == "c.":
            return f"{label} c. {number}"
        return f"{label} ({marker} {number})"
    si_label = _SI_LABELS.get(doc_type, "S.I.")
    return f"{label} ({si_label} {year}/{number})"


def enrich_legislation_payload(payload: dict[str, Any], ref: UkRef) -> dict[str, Any]:
    """Attach ``eli_uri`` / ``human_readable_citation`` / ``source_url`` to a payload.

    Does not mutate the input - returns a shallow copy.
    """
    out = dict(payload)
    title = payload.get("title")
    out["eli_uri"] = ref.id_uri
    out["human_readable_citation"] = human_readable_citation(
        ref.doc_type, ref.year, ref.number, title if isinstance(title, str) else None
    )
    out["source_url"] = ref.html_url
    return out


def parse_legislation_xml(xml_text: str) -> dict[str, Any]:
    """Parse a legislation.gov.uk ``data.xml`` document into a flat metadata dict.

    Reads the ``ukm:Metadata`` block (Dublin Core + ``ukm:PrimaryMetadata`` /
    ``ukm:SecondaryMetadata``). Tolerant: missing fields are simply omitted.
    """
    out: dict[str, Any] = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse legislation.gov.uk XML: {exc}") from exc

    out["document_uri"] = root.get("DocumentURI")
    out["id_uri"] = root.get("IdURI")
    out["restrict_extent"] = root.get("RestrictExtent")
    out["restrict_start_date"] = root.get("RestrictStartDate")

    meta = root.find(_q(LEG_NS, "Metadata")) or root.find(f".//{_q(UKM_NS, 'Metadata')}")
    if meta is None:
        # ukm:Metadata is namespaced with the ukm prefix directly under the root.
        for child in root:
            if child.tag == _q(UKM_NS, "Metadata"):
                meta = child
                break

    if meta is not None:
        title_el = meta.find(_q(DC_NS, "title"))
        if title_el is not None and title_el.text:
            out["title"] = title_el.text.strip()
        desc_el = meta.find(_q(DC_NS, "description"))
        if desc_el is not None and desc_el.text:
            out["description"] = desc_el.text.strip()
        modified_el = meta.find(_q(DC_NS, "modified"))
        if modified_el is not None and modified_el.text:
            out["date_modified"] = modified_el.text.strip()
        publisher_el = meta.find(_q(DC_NS, "publisher"))
        if publisher_el is not None and publisher_el.text:
            out["publisher"] = publisher_el.text.strip()

        primary = meta.find(_q(UKM_NS, "PrimaryMetadata"))
        secondary = meta.find(_q(UKM_NS, "SecondaryMetadata"))
        block = primary if primary is not None else secondary
        if block is not None:
            classification = block.find(_q(UKM_NS, "DocumentClassification"))
            if classification is not None:
                category = classification.find(_q(UKM_NS, "DocumentCategory"))
                if category is not None:
                    out["document_category"] = category.get("Value")
                main_type = classification.find(_q(UKM_NS, "DocumentMainType"))
                if main_type is not None:
                    out["document_main_type"] = main_type.get("Value")
                status = classification.find(_q(UKM_NS, "DocumentStatus"))
                if status is not None:
                    out["document_status"] = status.get("Value")
            year_el = block.find(_q(UKM_NS, "Year"))
            if year_el is not None:
                out["year"] = year_el.get("Value")
            number_el = block.find(_q(UKM_NS, "Number"))
            if number_el is not None:
                out["number"] = number_el.get("Value")
            enactment_el = block.find(_q(UKM_NS, "EnactmentDate"))
            if enactment_el is not None:
                out["enactment_date"] = enactment_el.get("Date")
            made_el = block.find(_q(UKM_NS, "Made"))
            if made_el is not None:
                out["made_date"] = made_el.get("Date")
            isbn_el = block.find(_q(UKM_NS, "ISBN"))
            if isbn_el is not None:
                out["isbn"] = isbn_el.get("Value")

    return out


def parse_search_feed(atom_text: str) -> tuple[int, list[dict[str, Any]]]:
    """Parse a legislation.gov.uk Atom search-results feed (``/data.feed``).

    Returns ``(total_estimate, items)``. ``total_estimate`` is best-effort: the feed
    exposes only ``leg:morePages`` (page count) and ``openSearch:itemsPerPage``, not a
    grand total, so callers should treat it as approximate when present, else None-like 0.
    """
    try:
        root = ET.fromstring(atom_text)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse legislation.gov.uk search feed: {exc}") from exc

    open_search_ns = "http://a9.com/-/spec/opensearch/1.1/"
    leg_ns = "http://www.legislation.gov.uk/namespaces/legislation"

    items_per_page_el = root.find(_q(open_search_ns, "itemsPerPage"))
    more_pages_el = root.find(_q(leg_ns, "morePages"))
    items_per_page = 0
    if items_per_page_el is not None and items_per_page_el.text:
        items_per_page = int(items_per_page_el.text)
    more_pages = 1
    if more_pages_el is not None and more_pages_el.text:
        more_pages = int(more_pages_el.text)

    items: list[dict[str, Any]] = []
    for entry in root.findall(_q(ATOM_NS, "entry")):
        item: dict[str, Any] = {}
        id_el = entry.find(_q(ATOM_NS, "id"))
        if id_el is not None and id_el.text:
            item["id_uri"] = id_el.text.strip()
        title_el = entry.find(_q(ATOM_NS, "title"))
        if title_el is not None and title_el.text:
            item["title"] = title_el.text.strip()
        summary_el = entry.find(_q(ATOM_NS, "summary"))
        if summary_el is not None and summary_el.text:
            item["description"] = summary_el.text.strip()
        published_el = entry.find(_q(ATOM_NS, "published"))
        if published_el is not None and published_el.text:
            item["published"] = published_el.text.strip()

        main_type_el = entry.find(_q(UKM_NS, "DocumentMainType"))
        if main_type_el is not None:
            item["document_main_type"] = main_type_el.get("Value")
        year_el = entry.find(_q(UKM_NS, "Year"))
        if year_el is not None:
            item["year"] = year_el.get("Value")
        number_el = entry.find(_q(UKM_NS, "Number"))
        if number_el is not None:
            item["number"] = number_el.get("Value")

        # Reference (type/year/number) is parsed from the canonical <id>.
        if item.get("id_uri"):
            try:
                ref = parse_reference(item["id_uri"])
                item["doc_type"] = ref.doc_type
            except ValueError:
                pass

        items.append(item)

    total_estimate = items_per_page * more_pages if items_per_page and more_pages else len(items)
    return total_estimate, items
