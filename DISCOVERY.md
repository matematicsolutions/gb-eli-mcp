# Discovery: legislation.gov.uk - United Kingdom

Date: 2026-07-06
Author: discovery commissioned by Wieslaw Mazur. **Status: CLOSED.** All probes below were
run live against production `www.legislation.gov.uk` before any code was written.

## Base site properties (CONFIRMED LIVE)

- **Base URL:** `https://www.legislation.gov.uk` (production, no beta/testphase distinction).
- **Authentication:** none - every probed endpoint returned HTTP 200 with no credential.
- **Rate limit:** none documented; own backoff + cache regardless (factory-standard policy).
- **Content negotiation:** the same URI path serves HTML (humans) or structured data
  (machines). Confirmed two ways:
  - `Accept: application/xml` header on the bare path
    (`GET /ukpga/2018/12` with `Accept: application/xml`) -> **200**, `Content-Type:
    application/xml;charset=utf-8`.
  - Explicit path suffix `/data.xml` (`GET /ukpga/2018/12/data.xml`) -> **200**, real
    structured XML (5.9 MB for the Data Protection Act 2018 body), root element
    `<Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation" ...
    xsi:schemaLocation="... http://www.legislation.gov.uk/schema/legislation.xsd">`.
  - The connector uses the **suffix form** (`/data.{format}`) - more robust across proxies/
    caches than relying on `Accept` header negotiation.
- **Per-item manifestation formats found in the metadata's own `atom:link rel="alternate"`
  entries:** `data.xml` (native schema), `data.rdf` (RDF/XML), `data.akn` (Akoma Ntoso!),
  `data.xht`/`data.htm`/`data.html` (HTML variants), `data.csv`, `data.pdf`, plus a link to
  the "Original PDF" scan. **`data.atom` on a single document returns 404** - Atom is a
  feed/search format only, not a per-document manifestation, unlike `data.xml`.
- **`/eli/` native path:** `GET https://www.legislation.gov.uk/eli/ukpga/2018/12` ->
  **HTTP 404**. legislation.gov.uk does NOT expose a native ELI namespace, despite its own
  identifier scheme predating and being closely related to ELI. See CONSTITUTION.md Art. 4
  for the disclosure this drives.
- **Licence:** confirmed live from the site's own `/help` page footer:
  `<a href=".../doc/open-government-licence/version/3" rel="license">Open Government
  Licence v3.0</a>`. OGL v3.0, as expected for UK government open data.
- **`/developer-guide` path:** returns 404 (no such page at that path on the current site;
  the developer documentation, if any, lives elsewhere or under a different name). Not
  blocking - the schema and search feed were fully discoverable by direct probing.

## Search (CONFIRMED LIVE)

- **Endpoint:** `/all/data.feed?text={query}` (global) or `/{doc_type}/data.feed?text=...`
  (scoped to one document type). Returns an Atom feed
  (`xmlns="http://www.w3.org/2005/Atom"`) with `openSearch:itemsPerPage`, `leg:page`,
  `leg:morePages` (no grand-total field), and one `<entry>` per hit.
- **Per-entry fields confirmed:** `id` (the canonical `.../id/{type}/{year}/{number}` URI),
  `title`, `summary`, `published`, `updated`, plus `ukm:DocumentMainType`, `ukm:Year`,
  `ukm:Number`, `ukm:CreationDate`, and per-format `atom:link rel="alternate"` entries
  (xml/rdf/akn/xht/html/csv/pdf) - example fetched live for `eur/2016/679` (UK GDPR).
- Live probe: `GET /all/data.feed?text=data%20protection` -> 200, 49,771 bytes, 12 more pages
  at 20 items/page (rough total ~240+ hits).

## Document-reference scheme (CONFIRMED LIVE across all 4 jurisdictions + UK-wide SI)

A reference is `/{doc_type}/{year}/{number}`, no query string. Point-in-time expressions add
a date segment: `/{doc_type}/{year}/{number}/{YYYY-MM-DD}`.

| doc_type | Jurisdiction | Probed live | Result |
|---|---|---|---|
| `ukpga` | UK Public General Act | `ukpga/2018/12` (Data Protection Act 2018) | 200, title "Data Protection Act 2018" |
| `uksi` | UK Statutory Instrument (UK-wide) | `uksi/2019/419` | 200, 941,146 bytes XML |
| `asp` | Act of the Scottish Parliament | `asp/2015/1` | 200, title "Food (Scotland) Act 2015" |
| `nia` | Act of the Northern Ireland Assembly | `nia/2016/8` | 200, title "Special Educational Needs and Disability Act (Northern Ireland) 2016" |
| `wsi` | Wales Statutory Instrument | `wsi/2020/1` | 200, title "The Police Appeals Tribunals Rules 2020" |
| `eur` | Retained/assimilated EU Regulation | `eur/2016/679` (UK GDPR) | 200 (seen via search feed entry) |

Additional documented type codes not separately probed but following the same scheme:
`ssi` (Scottish SI), `nisr` (NI Statutory Rule), `anaw` (Act of the Senedd/National Assembly
for Wales), `ukla` (UK Local Act) - all resolve under the same `/{type}/{year}/{number}` path
convention published by legislation.gov.uk.

## Metadata schema (CONFIRMED LIVE, for the citation contract)

From `GET /ukpga/2018/12/data.xml`, the `ukm:Metadata` block (namespace
`http://www.legislation.gov.uk/namespaces/metadata`) carries, inside Dublin Core +
`ukm:PrimaryMetadata`/`ukm:SecondaryMetadata`:

- `dc:identifier`, `dc:title`, `dc:description`, `dc:modified`, `dc:publisher`
- `ukm:DocumentClassification` -> `ukm:DocumentCategory` (`Value="primary"` etc.),
  `ukm:DocumentMainType` (e.g. `Value="UnitedKingdomPublicGeneralAct"`), `ukm:DocumentStatus`
  (e.g. `Value="revised"`)
- `ukm:Year` (`Value="2018"`), `ukm:Number` (`Value="12"`)
- `ukm:EnactmentDate` (`Date="2018-05-23"`) for Acts / `ukm:Made` for instruments
- `ukm:ISBN`
- `ukm:UnappliedEffects` - a list of pending/not-yet-applied amendments affecting the text
  (used to justify the "revised vs as-enacted" caveat in CONSTITUTION.md).
- Root element attributes: `DocumentURI`, `IdURI`, `NumberOfProvisions`, `RestrictExtent`
  (e.g. `"E+W+S+N.I."`), `RestrictStartDate` (the point-in-time this revised text reflects).

## Mapping to the 4 super-tools (CONFIRMED)

| Super-tool | Endpoint | Notes |
|---|---|---|
| `gb_search` | `/all/data.feed` or `/{doc_type}/data.feed` (`text`, `year`, `page`) | Atom search feed; `total_estimate` derived from `itemsPerPage x morePages` |
| `gb_get_act` | `/{doc_type}/{year}/{number}[/{date}]/data.xml` | metadata via `ukm:Metadata` |
| `gb_get_text` | `/{doc_type}/{year}/{number}[/{date}]/data.{xml,html,akn,rdf,pdf,csv}` | format selected by suffix |
| `gb_recent_legislation` | `/{doc_type}/data.feed?year=...` filtered client-side by `published` | no generic cross-type `dateFrom`; scoped by year then filtered |

## Citation contract (Article IV) - CLOSED for GB

- `eli_uri` = `https://www.legislation.gov.uk/id/{type}/{year}/{number}[/{date}]` - the UK's
  own persistent id URI. **NOT a native ELI** (confirmed 404 on `/eli/...` - see above);
  documented as such per Art. 4 and matching the `nl-eli-mcp`/`se-eli-mcp` disclosure pattern.
- `human_readable_citation` = UK convention, e.g. `"Data Protection Act 2018 c. 12"` or
  `"The Police Appeals Tribunals Rules 2020 (S.I. 2020/1)"`.
- `source_url` = the browsable legislation.gov.uk page (`/{type}/{year}/{number}[/{date}]`).

## Decision: BUILD

All blocking questions resolved in favour: (1) structured XML confirmed real, not HTML;
(2) no native `/eli/` -> honest disclosure pattern applied (not a compromise, a documented
choice); (3) keyless, confirmed live; (4) licence confirmed OGL v3.0 from the site itself.
Reuse from `de-eli-mcp`/`fi-eli-mcp` is high for the skeleton (audit.py, cache.py copied
verbatim); `citations.py`/`client.py`/`models.py` are new, built for legislation.gov.uk's
actual XML schema + Atom search feed shape.

## Next step

Build `gb-eli-mcp` per the factory skeleton: `client.py` (httpx + cache, `/data.{fmt}` path
negotiation), `citations.py` (reference parsing + UK citation convention +
`legislation.xsd`/Atom parsing via stdlib `ElementTree`), `models.py` (tolerant Pydantic v2),
`server.py` (4 tools: `gb_search`, `gb_get_act`, `gb_get_text`, `gb_recent_legislation`).
