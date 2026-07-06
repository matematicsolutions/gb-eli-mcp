# Constitution of gb-eli-mcp

Version: 0.2.0
Date: 2026-07-06
Licence: Apache-2.0

`gb-eli-mcp` is an MCP server for **legislation.gov.uk** and **Find Case Law**
(caselaw.nationalarchives.gov.uk), both maintained by The National Archives - the
official, public sources of United Kingdom legislation (Acts of the UK Parliament, UK
Statutory Instruments, and the equivalent instruments of the Scottish Parliament, Senedd
Cymru/Welsh Parliament, and Northern Ireland Assembly) and UK case law (judgments of the
Court of Appeal, High Court divisions, Upper Tribunal, First-tier Tribunal, Family Court,
and other courts/tribunals). Legislation coverage (v0.1.0) has search, act/instrument
metadata, full-text retrieval, and a recent-changes feed. Case law coverage (v0.2.0,
added 2026-07-06) closes the connector's one remaining gap: `gb_search_case_law` and
`gb_get_case` wrap the Find Case Law Atom feed - keyless, public, Open Justice Licence.
Note: at the time this feature was built, the `worldwidelaw/legal-sources` catalog had
**no UK/GB case-law collector** listed (confirmed by direct GitHub directory
enumeration) - this is original work built from first-hand live verification of the Find
Case Law service, not a port of an existing connector.

The 4 principles below are inherited from the `eu-legal-mcp` line Constitution (Article IV).

---

## Art. 1. Public data only

`https://www.legislation.gov.uk` and `https://caselaw.nationalarchives.gov.uk` (both The
National Archives) are the official, public sources of UK legislation and UK case law
respectively. legislation.gov.uk content is published under the **Open Government Licence
v3.0** (confirmed live from the site's own `/help` page footer). Find Case Law content is
published under the **Open Justice Licence** (confirmed live from the feed's own licence
link). Both permit copying, publishing and adapting with attribution. The server is
read-only against both hosts and sends nothing beyond the requested reference / search
terms.

## Art. 2. Mandatory audit log

Every call to every MCP tool MUST be written to `~/.matematic/audit/gb-eli-mcp.jsonl` as one
JSON line (ts / tool / input_hash SHA-256 / output_count_or_size / duration_ms / status).
Inability to write = the tool returns an error, it does not silently skip.

## Art. 3. Vendor neutrality

No tool hardcodes an LLM provider, assumes a model, or introduces commercial telemetry. The
server communicates only with `www.legislation.gov.uk`, `caselaw.nationalarchives.gov.uk`,
and the local filesystem. Authentication: **no API key** on either host (confirmed live -
every probed endpoint on both services returned 200 with no credential). No documented rate
limit on either service; own backoff + cache regardless (this factory's standing policy).

## Art. 4. Persistent identifier and human-readable citation are mandatory

Every response MUST carry three fields:

- `eli_uri`: **legislation.gov.uk has NO native `/eli/` namespace** - confirmed live by
  probing `GET https://www.legislation.gov.uk/eli/ukpga/2018/12`, which returns HTTP 404.
  legislation.gov.uk's own persistent-identifier scheme (`https://www.legislation.gov.uk/id/{type}/{year}/{number}[/{date}]`)
  predates and is closely related to ELI - the UK is widely credited with pioneering the
  URI-based legislation-identifier concept that ELI later formalised EU-wide - but it is not
  itself published under an `/eli/` path. Per this factory's disclosure pattern (matching
  `nl-eli-mcp` and `se-eli-mcp`), `eli_uri` therefore carries the UK's own stable id URI
  **instead of a fabricated ELI path**, and every tool response's `dataset_note` restates this
  explicitly so no downstream consumer mistakes it for a native ELI.
- `human_readable_citation`: the UK legal citation convention - e.g. `"Data Protection Act 2018 c. 12"`
  for a public general Act (chapter number), or `"The Police Appeals Tribunals Rules 2020 (S.I. 2020/1)"`
  for a statutory instrument. Devolved-legislature Acts use their own chapter-letter series
  (`asp` for Scotland, `anaw` for Wales) rather than `c.`.
- `source_url`: the browsable legislation.gov.uk page for that version (work or point-in-time
  expression).

## Art. 5. Case-law citation contract (Find Case Law)

Every `gb_search_case_law` / `gb_get_case` response MUST carry:

- `human_readable_citation`: the UK neutral citation convention combined with the case
  name where available, e.g. `"Example v Another Example [2026] EWHC 1658 (Admin)"`.
- `source_url`: the browsable Find Case Law page for the judgment.
- `dataset_note`: restates that Find Case Law is a separate service from
  legislation.gov.uk with its own identifier scheme, and that only pre-April-2025
  documents have a URI derivable directly from the neutral citation
  (`/{court}/{year}/{number}`) - documents from April 2025 onward use an opaque
  `d-{uuid}` id (`fclid`) that requires a search round-trip to resolve.

---

## Open points (do not block the build)

1. **Revised vs as-enacted text.** legislation.gov.uk publishes a continuously updated
   ("as amended") consolidated text alongside the original ("as enacted"/"as made") text, and
   surfaces unapplied/pending amendments in its metadata (`ukm:UnappliedEffects`). `gb_get_act`
   /`gb_get_text` surface `restrict_start_date` and the `dataset_note` so a caller does not
   mistake a point-in-time expression for the fully up-to-date state.
2. **No exhaustive search API.** legislation.gov.uk exposes an Atom search feed
   (`/all/data.feed?text=...` or `/{type}/data.feed?...`) with `text`/`year`/`page` filters, not
   a general-purpose query language. `gb_search`'s `total_estimate` is derived from
   `itemsPerPage x morePages` (the feed does not expose a grand total) and is therefore
   approximate.
3. **Case law - resolved in v0.2.0.** UK court decisions (Find Case Law,
   caselaw.nationalarchives.gov.uk) are covered by `gb_search_case_law`/`gb_get_case`. One
   residual limitation: the public API has no documented server-side date-range filter, so
   `from_date`/`to_date` are applied client-side after fetching (same class of limitation as
   legislation.gov.uk's search feed having no cross-type `dateFrom`). A second residual
   limitation: documents published from April 2025 onward use an opaque `d-{uuid}` URI that
   cannot be derived from the neutral citation alone (pre-2025 documents can).
4. **Devolved-legislature nuance.** Wales SIs (`wsi`) are numbered in the shared UK S.I. series
   unless suffixed "(W.)"; the citation helper labels them `S.I.` accordingly, which is a
   simplification worth revisiting if a client needs the Welsh-specific numbering distinction.

## Constitution evolution

Changes to art. 1-5 follow SEMVER + an entry in `CHANGELOG.md` + a `pyproject.toml` bump.

- **v0.2.0 (2026-07-06):** added Art. 5 (case-law citation contract) and extended Art. 1/3
  to cover the second host (`caselaw.nationalarchives.gov.uk`), following the addition of
  `gb_search_case_law`/`gb_get_case`. Art. 1-4 substance unchanged for legislation.gov.uk.

First version: 2026-07-06. Author: Wieslaw Mazur / MateMatic.
