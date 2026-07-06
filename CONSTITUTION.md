# Constitution of gb-eli-mcp

Version: 0.1.0
Date: 2026-07-06
Licence: Apache-2.0

`gb-eli-mcp` is an MCP server for **legislation.gov.uk**, maintained by The National
Archives - the official, public source of United Kingdom legislation (Acts of the UK
Parliament, UK Statutory Instruments, and the equivalent instruments of the Scottish
Parliament, Senedd Cymru/Welsh Parliament, and Northern Ireland Assembly). The MVP covers
search, act/instrument metadata, full-text retrieval, and a recent-changes feed. Case
law (UK courts, e.g. via The National Archives' Find Case Law / caselaw.nationalarchives.gov.uk)
is a later, separate feature.

The 4 principles below are inherited from the `eu-legal-mcp` line Constitution (Article IV).

---

## Art. 1. Public data only

`https://www.legislation.gov.uk` (The National Archives) is the official, public source of
UK legislation. Content is published under the **Open Government Licence v3.0** (confirmed
live from the site's own `/help` page footer: "Open Government Licence v3.0"), which permits
copying, publishing and adapting with attribution. The server is read-only against
legislation.gov.uk and sends nothing beyond the requested reference / search terms.

## Art. 2. Mandatory audit log

Every call to every MCP tool MUST be written to `~/.matematic/audit/gb-eli-mcp.jsonl` as one
JSON line (ts / tool / input_hash SHA-256 / output_count_or_size / duration_ms / status).
Inability to write = the tool returns an error, it does not silently skip.

## Art. 3. Vendor neutrality

No tool hardcodes an LLM provider, assumes a model, or introduces commercial telemetry. The
server communicates only with `www.legislation.gov.uk` and the local filesystem.
Authentication: **no API key** (confirmed live - every probed endpoint returned 200 with no
credential). No documented rate limit; own backoff + cache regardless (this factory's
standing policy).

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
3. **Case law.** UK court decisions (Find Case Law, caselaw.nationalarchives.gov.uk) are a
   separate National Archives service with its own API; a later, separate tool family.
4. **Devolved-legislature nuance.** Wales SIs (`wsi`) are numbered in the shared UK S.I. series
   unless suffixed "(W.)"; the citation helper labels them `S.I.` accordingly, which is a
   simplification worth revisiting if a client needs the Welsh-specific numbering distinction.

## Constitution evolution

Changes to art. 1-4 follow SEMVER + an entry in `CHANGELOG.md` + a `pyproject.toml` bump.

First version: 2026-07-06. Author: Wieslaw Mazur / MateMatic.
