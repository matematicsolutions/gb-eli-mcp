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

import json
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


# ---------------------------------------------------------------------------
# The National Archives' Find Case Law (caselaw.nationalarchives.gov.uk)
#
# A separate service from legislation.gov.uk (different host, different Atom
# dialect - TNA namespace instead of leg:/ukm:), added for UK case law
# coverage. Confirmed live 2026-07-06: keyless, public, Open Justice Licence.
# See DISCOVERY.md "Find Case Law" section for the full live-probe record.
# ---------------------------------------------------------------------------

CASELAW_BASE_URL = "https://caselaw.nationalarchives.gov.uk"
TNA_NS = "https://caselaw.nationalarchives.gov.uk"

# Neutral citation court abbreviation -> Find Case Law URI court-path segment.
# Only pre-April-2025 style citations resolve directly to a "/{court}/{year}/{number}"
# URI (confirmed live: https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658).
# Post-April-2025 documents use an opaque "d-{uuid}" URI instead (per the service's own
# OpenAPI docs) and cannot be derived from the citation alone - gb_get_case falls back to
# a query search for those.
_NCN_RE = re.compile(
    r"\[(?P<year>\d{4})\]\s*"
    r"(?P<court>UKSC|UKPC|EWCA|EWHC|EWCOP|EWFC|UKUT|UKFTT|UKEAT|UKET|EAT)\s*"
    r"(?P<division>Civ|Crim|Ch|Fam|Admin|Comm|TCC|Patents|IPEC|KB|QB|Mercantile)?\s*"
    r"(?P<number>\d+)\s*"
    r"(?:\((?P<paren_division>[\w\s]+)\))?",
    re.IGNORECASE,
)

# Court codes that need no division sub-path (top-level courts).
_COURT_NO_DIVISION = {"uksc", "ukpc", "ewca"}


@dataclass(frozen=True)
class NeutralCitation:
    """A parsed UK neutral citation number (NCN), e.g. '[2026] EWHC 1658 (Admin)'."""

    year: str
    court: str  # lowercased, e.g. "ewhc"
    division: str | None  # lowercased, e.g. "admin"
    number: str
    raw: str

    @property
    def court_path(self) -> str:
        """Find Case Law URI court-path segment, e.g. 'ewhc/admin' or 'ewca/civ'."""
        if self.division:
            return f"{self.court}/{self.division}"
        return self.court

    @property
    def uri_path(self) -> str:
        """Best-effort Find Case Law URI path (pre-2025 style): '/{court}/{year}/{number}'."""
        return f"/{self.court_path}/{self.year}/{self.number}"

    @property
    def data_xml_url(self) -> str:
        return f"{CASELAW_BASE_URL}{self.uri_path}/data.xml"

    @property
    def html_url(self) -> str:
        return f"{CASELAW_BASE_URL}{self.uri_path}"


def parse_neutral_citation(value: str) -> NeutralCitation:
    """Parse a UK neutral citation, e.g. ``"[2026] EWHC 1658 (Admin)"`` or
    ``"[2024] EWCA Civ 12"``.

    Raises ``ValueError`` on unparseable input.
    """
    raw = value.strip()
    m = _NCN_RE.search(raw)
    if m is None:
        raise ValueError(
            f"Not a recognisable UK neutral citation: {value!r}. "
            f"Expected e.g. '[2026] EWHC 1658 (Admin)' or '[2024] EWCA Civ 12'."
        )
    court = m.group("court").lower()
    division = (m.group("division") or m.group("paren_division") or "").strip().lower() or None
    if division:
        division = division.replace(" ", "")
    if court in _COURT_NO_DIVISION and division is None:
        pass  # e.g. UKSC, UKPC, and bare EWCA numbers with division inline already
    return NeutralCitation(
        year=m.group("year"),
        court=court,
        division=division,
        number=m.group("number"),
        raw=raw,
    )


def parse_caselaw_uri(value: str) -> str:
    """Normalise a Find Case Law reference (URI, path, or bare id) to a URI path.

    Accepts a full URL (``https://caselaw.nationalarchives.gov.uk/ewhc/admin/2026/1658``),
    a bare path (``/ewhc/admin/2026/1658`` or ``ewhc/admin/2026/1658``), or an opaque
    UUID-style id (``d-f11e093f-...``, used for documents published from April 2025
    onward - see module docstring).
    """
    raw = value.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        after_scheme = raw.split("://", 1)[1]
        path = after_scheme.split("/", 1)[1] if "/" in after_scheme else ""
        raw = "/" + path
    if not raw.startswith("/"):
        raw = "/" + raw
    # Strip a trailing /data.xml or similar manifestation suffix if present.
    raw = re.sub(r"/data\.\w+$", "", raw)
    return raw.rstrip("/")


def human_readable_case_citation(neutral_citation: str | None, title: str | None) -> str:
    """UK case citation convention: "{Case name} {Neutral Citation}"."""
    if title and neutral_citation:
        return f"{title} {neutral_citation}"
    return neutral_citation or title or "Unknown case"


def parse_caselaw_feed(atom_text: str) -> tuple[int, list[dict[str, Any]]]:
    """Parse a Find Case Law Atom feed (``/atom.xml``) into ``(total_estimate, items)``.

    Uses the ``tna:`` namespace (``https://caselaw.nationalarchives.gov.uk``) alongside
    plain Atom. ``total_estimate`` is derived from the ``rel="last"`` pagination link's
    ``page=`` query param x ``per_page`` (the feed does not expose a grand total field,
    same limitation as legislation.gov.uk's search feed).
    """
    try:
        root = ET.fromstring(atom_text)
    except ET.ParseError as exc:
        raise ValueError(f"Could not parse Find Case Law Atom feed: {exc}") from exc

    last_pages = 1
    per_page = 50
    for link in root.findall(_q(ATOM_NS, "link")):
        if link.get("rel") == "last":
            href = link.get("href") or ""
            m = re.search(r"page=(\d+)", href)
            if m:
                last_pages = int(m.group(1))
            m2 = re.search(r"per_page=(\d+)", href)
            if m2:
                per_page = int(m2.group(1))

    items: list[dict[str, Any]] = []
    for entry in root.findall(_q(ATOM_NS, "entry")):
        item: dict[str, Any] = {}
        id_el = entry.find(_q(ATOM_NS, "id"))
        if id_el is not None and id_el.text:
            item["id"] = id_el.text.strip()
        title_el = entry.find(_q(ATOM_NS, "title"))
        if title_el is not None and title_el.text:
            item["title"] = title_el.text.strip()
        author_el = entry.find(_q(ATOM_NS, "author"))
        if author_el is not None:
            name_el = author_el.find(_q(ATOM_NS, "name"))
            if name_el is not None and name_el.text:
                item["court"] = name_el.text.strip()
        published_el = entry.find(_q(ATOM_NS, "published"))
        if published_el is not None and published_el.text:
            item["date"] = published_el.text.strip()

        # Prefer the identifier explicitly typed "ukncn" (neutral citation number) -
        # confirmed live 2026-07-06. Some feed variants omit @type on that element, so
        # fall back to "whichever identifier isn't @type='fclid'" if no ukncn is found.
        fallback_citation: str | None = None
        for identifier_el in entry.findall(_q(TNA_NS, "identifier")):
            id_type = identifier_el.get("type")
            if id_type == "ukncn" and identifier_el.text:
                item["neutral_citation"] = identifier_el.text.strip()
            elif id_type == "fclid" and identifier_el.text:
                item["fclid"] = identifier_el.text.strip()
            elif id_type is None and identifier_el.text:
                fallback_citation = identifier_el.text.strip()
        if "neutral_citation" not in item and fallback_citation:
            item["neutral_citation"] = fallback_citation

        uri_el = entry.find(_q(TNA_NS, "uri"))
        if uri_el is not None and uri_el.text:
            item["uri"] = uri_el.text.strip()

        html_url = None
        pdf_url = None
        xml_url = None
        for link in entry.findall(_q(ATOM_NS, "link")):
            href = link.get("href") or ""
            rel = link.get("rel")
            if rel == "alternate" and not href.endswith((".pdf", ".xml")):
                html_url = href
            elif href.endswith(".pdf"):
                pdf_url = href
            elif href.endswith(".xml"):
                xml_url = href
        if html_url:
            item["source_url"] = html_url
        if pdf_url:
            item["pdf_url"] = pdf_url
        if xml_url:
            item["akn_url"] = xml_url

        items.append(item)

    total_estimate = last_pages * per_page
    return total_estimate, items


# ---------------------------------------------------------------------------
# GOV.UK Search API + Content API (www.gov.uk/api/search.json, /api/content/...)
#
# One upstream aggregating many institutions' documents: employment tribunal
# decisions, employment appeal tribunal decisions, tax tribunal decisions,
# Upper Tribunal (AAC) decisions, residential property tribunal decisions,
# HMRC internal manuals and CMA competition cases. Confirmed live 2026-07-07:
# keyless JSON with a dedicated `total` field. Content is Crown copyright,
# published under the Open Government Licence v3.0 (site-wide licence).
# ---------------------------------------------------------------------------

GOVUK_BASE_URL = "https://www.gov.uk"


def parse_govuk_search_json(json_text: str) -> tuple[int, list[dict[str, Any]]]:
    """Parse a GOV.UK Search API response into ``(total, items)``.

    Unlike the two Atom feeds above, GOV.UK exposes a REAL grand total in a dedicated
    ``total`` field (verified live 2026-07-07 against the per-type facet counts) - no
    page-count estimation needed.
    """
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse GOV.UK Search API JSON: {exc}") from exc
    if not isinstance(data, dict) or "results" not in data:
        raise ValueError("GOV.UK Search API JSON has no 'results' field.")

    total = int(data.get("total") or 0)
    items: list[dict[str, Any]] = []
    for res in data.get("results") or []:
        if not isinstance(res, dict):
            continue
        item: dict[str, Any] = {
            "title": res.get("title"),
            "description": res.get("description"),
            "link": res.get("link"),
            "document_type": res.get("content_store_document_type"),
            "public_timestamp": res.get("public_timestamp"),
        }
        orgs = res.get("organisations")
        if isinstance(orgs, list):
            names = [o.get("title") for o in orgs if isinstance(o, dict) and o.get("title")]
            if names:
                item["organisations"] = names
        link = item.get("link")
        if isinstance(link, str) and link:
            item["source_url"] = (
                link if link.startswith("http") else f"{GOVUK_BASE_URL}{link}"
            )
        items.append({k: v for k, v in item.items() if v is not None})
    return total, items


def parse_govuk_content_json(json_text: str) -> dict[str, Any]:
    """Parse a GOV.UK Content API response into a flat metadata + body dict.

    Extracts ``title``, ``document_type``, ``public_updated_at``, ``first_published_at``,
    the HTML ``body`` from ``details`` and any ``attachments`` (title/url/content_type) -
    tribunal decisions on GOV.UK carry the judgment as a PDF attachment with a short
    HTML body, HMRC manual sections carry the full text in the body (verified live
    2026-07-07). Tolerant: missing fields are simply omitted.
    """
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not parse GOV.UK Content API JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("GOV.UK Content API JSON is not an object.")

    out: dict[str, Any] = {}
    for key in ("title", "description", "document_type", "base_path",
                "public_updated_at", "first_published_at"):
        value = data.get(key)
        if value:
            out[key] = value

    details = data.get("details")
    if isinstance(details, dict):
        body = details.get("body")
        if isinstance(body, str) and body:
            out["body_html"] = body
        elif isinstance(body, list):
            # Some content schemas (e.g. HMRC manual sections) hold a list of
            # {content_type, content} parts - take the html one.
            for part in body:
                if isinstance(part, dict) and part.get("content_type") == "text/html":
                    out["body_html"] = part.get("content")
                    break
        attachments = details.get("attachments")
        if isinstance(attachments, list):
            out["attachments"] = [
                {
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "content_type": a.get("content_type"),
                }
                for a in attachments
                if isinstance(a, dict) and a.get("url")
            ]
        metadata = details.get("metadata")
        if isinstance(metadata, dict):
            for key in ("tribunal_decision_country", "tribunal_decision_categories",
                        "tribunal_decision_decision_date", "hearing_date",
                        "opened_date", "closed_date", "case_state", "case_type"):
                if metadata.get(key):
                    out[key] = metadata[key]

    base_path = data.get("base_path")
    if isinstance(base_path, str) and base_path:
        out["source_url"] = f"{GOVUK_BASE_URL}{base_path}"
    return out


def human_readable_govuk_citation(
    title: str | None, document_type: str | None, date: str | None
) -> str:
    """Human-readable citation for a GOV.UK document.

    GOV.UK documents have no neutral-citation convention; the honest citation is
    "{Title} ({document type label}, {date}, GOV.UK)".
    """
    label = title or "Untitled GOV.UK document"
    type_label = (document_type or "").replace("_", " ").strip()
    day = (date or "")[:10]
    qualifier = ", ".join(p for p in (type_label, day) if p)
    return f"{label} ({qualifier}, GOV.UK)" if qualifier else f"{label} (GOV.UK)"


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
