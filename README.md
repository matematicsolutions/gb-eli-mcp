# gb-eli-mcp

<!-- mcp-name: io.github.matematicsolutions/gb-eli-mcp -->

An MCP server for **legislation.gov.uk**, The National Archives' official portal for
United Kingdom legislation. It searches and retrieves Acts of Parliament, UK Statutory
Instruments, and the equivalent instruments of the Scottish Parliament, Senedd
Cymru/Welsh Parliament and Northern Ireland Assembly, with persistent identifiers and
verifiable citations.

Part of the MateMatic `eu-legal-mcp` production line: the UK counterpart of the Polish
`sejm-eli-mcp` and the German `de-eli-mcp`, built on the same architecture and citation
contract against the UK's own source.

> **No native ELI.** legislation.gov.uk does not publish a native `/eli/` namespace
> (confirmed live: `GET /eli/ukpga/2018/12` returns 404), even though its own
> persistent-identifier scheme predates and is closely related to ELI - the UK is widely
> credited with pioneering the URI-based legislation-identifier concept that ELI later
> formalised EU-wide. `eli_uri` therefore carries the UK's own stable id URI
> (`https://www.legislation.gov.uk/id/{type}/{year}/{number}`) instead of a fabricated
> ELI path - the same disclosure pattern used by this factory's `nl-eli-mcp` and
> `se-eli-mcp`. See `CONSTITUTION.md` Art. 4.
>
> **Licence.** Content is published under the **Open Government Licence v3.0**
> (confirmed live from the site's own `/help` page), which permits copying, publishing
> and adapting with attribution. This connector only relays that public content, with a
> `source_url` on every response.

## The eight tools

| Tool | What it does |
|---|---|
| `gb_search` | Search legislation by text, doc type and year (`/all/data.feed` or `/{doc_type}/data.feed`). |
| `gb_get_act` | Fetch act/instrument metadata by reference (e.g. `ukpga/2018/12`). |
| `gb_get_text` | Fetch the full text (`xml`, `html`, `akn`/Akoma Ntoso, `rdf`, `pdf`, `csv`). |
| `gb_recent_legislation` | Legislation published since a date, newest-first, optionally by doc type. |
| `gb_search_case_law` | Search UK judgments via The National Archives' Find Case Law Atom feed, by text, court, and date range. |
| `gb_get_case` | Fetch a judgment by neutral citation, Find Case Law URI/path, or opaque id - returns Akoma Ntoso XML, or a PDF link fallback. |
| `gb_search_govuk` | Search GOV.UK documents via the keyless Search API - employment/tax/property tribunal decisions, HMRC internal manuals, CMA cases - with server-side date filters and real totals. |
| `gb_get_govuk_content` | Fetch one GOV.UK document via the Content API - tribunal decisions return the judgment PDF link, HMRC manual sections return the full text. |

### GOV.UK coverage (added v0.3.0, feature-003)

One upstream, many institutions: `gb_search_govuk` filters by `document_type`.
Live-verified totals (2026-07-07, from the Search API's own `total`/facet fields -
probe: `https://www.gov.uk/api/search.json?count=0&facet_content_store_document_type=1000`):

| `document_type` | Documents |
|---|---|
| `employment_tribunal_decision` | 132,162 |
| `hmrc_manual_section` | 85,315 |
| `residential_property_tribunal_decision` | 17,088 |
| `employment_appeal_tribunal_decision` | 2,571 |
| `cma_case` | 2,565 |
| `utaac_decision` (Upper Tribunal, AAC) | 2,031 |
| `tax_tribunal_decision` | 1,414 |
| `asylum_support_decision` | 101 |

See `SOURCES.md` for the full per-source ledger, including what was scouted and
deliberately rejected (ICO, FCA, IAC) and why.

Every response carries the contract: `eli_uri`
(e.g. `https://www.legislation.gov.uk/id/ukpga/2018/12`), `human_readable_citation`
(e.g. `Data Protection Act 2018 c. 12`), and `source_url`. Case-law responses carry the
same-spirit contract (`human_readable_citation`, `source_url`, `dataset_note`) - see
`CONSTITUTION.md` Art. 5.

## Install

```bash
cd gb-eli-mcp
pip install -e .
```

## Configure (Claude Code / any MCP client)

Copy `.mcp.json.example` and adjust if needed:

```json
{
  "mcpServers": {
    "gb-eli-mcp": { "command": "gb-eli-mcp" }
  }
}
```

### Windows 11 ze Smart App Control

Smart App Control blokuje niepodpisane pliki wykonywalne, a `uvx.exe`, `pip.exe`
i generowany przy instalacji `gb-eli-mcp.exe` podpisane nie sa. `python.exe`
z python.org jest podpisany przez Python Software Foundation, wiec uruchomienie
przez modul omija blokade:

```bash
python -m pip install gb-eli-mcp
python -m gb_eli_mcp
```

```json
{ "mcpServers": { "gb-eli-mcp": { "command": "python", "args": ["-m", "gb_eli_mcp"] } } }
```

Nie wylaczaj Smart App Control, zeby to obejsc - wylaczenia nie da sie cofnac
bez ponownej instalacji systemu.

Environment:

- `GB_ELI_BASE_URL` - default `https://www.legislation.gov.uk`
- `GB_ELI_CASELAW_BASE_URL` - default `https://caselaw.nationalarchives.gov.uk`
- `GB_ELI_GOVUK_BASE_URL` - default `https://www.gov.uk`
- `GB_ELI_CACHE_DIR` - default `~/.matematic/cache/gb-eli`
- `GB_ELI_AUDIT_DIR` - default `~/.matematic/audit`

No API key. legislation.gov.uk is keyless.

## Governance

- **Public data only** - read-only against legislation.gov.uk; no client data leaves the
  machine beyond search parameters.
- **Audit log** - every tool call appends one JSON line to
  `~/.matematic/audit/gb-eli-mcp.jsonl`.
- **Vendor-neutral** - the server talks only to legislation.gov.uk and the local
  filesystem; no LLM provider, no telemetry.
- **Verifiable citations** - every response is independently checkable via `source_url`.

See `CONSTITUTION.md` (the binding rules) and `DISCOVERY.md` (the live API probe).

## Tests

```bash
pip install -e ".[dev]"
pytest tests/test_instructions_drift.py -v   # offline
pytest tests/test_citations_case_law.py -v   # offline
pytest tests/test_citations_govuk.py -v      # offline
pytest tests/test_smoke.py -v                # hits live legislation.gov.uk
pytest tests/test_smoke_case_law.py -v       # hits live caselaw.nationalarchives.gov.uk
pytest tests/test_smoke_govuk.py -v          # hits live www.gov.uk
```

## Licence

Apache-2.0. (c) Matematic Solutions / Wieslaw Mazur.

Note: the *code* in this repository is Apache-2.0. The *legislation content* fetched at
runtime from legislation.gov.uk remains Crown copyright, published under the Open
Government Licence v3.0 - not relicensed by this project.
