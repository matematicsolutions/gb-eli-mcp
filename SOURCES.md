# Sources ledger - United Kingdom (UK)

Machine-diffable record of every Legal Data Hunter (`worldwidelaw/legal-sources`) source we have
checked for this country, and what we did about it. Purpose: the next gap-audit (PLAYBOOK.md
section 8) is a file diff against a fresh `manifest.yaml`, not a re-run of hours of research.

Update this file every time a widen-round touches this country. One row per LDH source `id`.
LDH uses the country code `UK`, not ISO `GB` (gap_scan.py maps GB -> UK).

## Narrative notes per source (2026-07-07 widen-round, feature-003)

**GOV.UK Search API + Content API** (`gb_search_govuk`, `gb_get_govuk_content`) - one keyless
upstream aggregating many institutions' documents on www.gov.uk. Live-verified totals from the
API's own `total`/facet fields (probe:
`https://www.gov.uk/api/search.json?count=0&facet_content_store_document_type=1000`, cross-checked
per type via `?filter_content_store_document_type={type}&count=0`):
`employment_tribunal_decision` 132,162; `hmrc_manual_section` 85,315;
`residential_property_tribunal_decision` 17,088; `employment_appeal_tribunal_decision` 2,571;
`cma_case` 2,565; `utaac_decision` 2,031; `tax_tribunal_decision` 1,414;
`asylum_support_decision` 101. Server-side date filter confirmed
(`filter_public_timestamp=from:...,to:...`). Content API (`/api/content/{path}`) confirmed:
tribunal decisions carry the judgment as a PDF attachment with a short HTML body; HMRC manual
sections carry the full text in the body. This one client legitimately covers UK/ET, UK/HMRC,
UK/HMRC-Manuals, UK/CMA and UK/FTT-Tax at once (PLAYBOOK section 8.5: prefer one client where
the upstream aggregates).

**Find Case Law / JCPC** - the existing `gb_search_case_law`/`gb_get_case` tools (v0.2.0) already
cover the Privy Council: confirmed live 2026-07-07,
`https://caselaw.nationalarchives.gov.uk/atom.xml?court=ukpc&per_page=5` returns a Privy Council
feed with `rel="last"` page 71 (~355 documents). UK/CaseLaw, UK/FindCaseLaw and UK/JCPC-Crown are
therefore all shipped under the existing tools - nothing new was built for them.

**UK/IAC (rejected, `bot_protection`)** - Immigration & Asylum Chamber decisions are NOT on
www.gov.uk (`/immigration-asylum-tribunal-decisions` returns 404); they live on
`tribunalsdecisions.service.gov.uk`, whose machine endpoints reject non-browser clients:
`GET /utiac.json` returns 406 `{"msg":"<br/>UTIAC<br/>Agent not allowed<br/>"}` even with a
browser User-Agent (probed live 2026-07-07). The HTML page returns 200, but an HTML-only,
agent-blocking service is not safe to expose as a lookup tool.

**UK/ICO (rejected, `no_machine_readable_api`)** - `ico.org.uk/action-weve-taken/enforcement/`
is reachable (HTTP 200, no bot wall at probe time 2026-07-07) but is a server-rendered HTML
facet listing with no JSON/Atom/API alternative and no total field; a screen-scrape would break
silently and cannot honour the exact-match citation contract.

**UK/FCA (rejected, `undocumented_third_party_search_backend`)** - fca.org.uk search is served
by an internal Funnelback cloud (`fcauk-search.funnelback.squiz.cloud`, found in the page's
drupal-settings JSON, probed 2026-07-07), not an official documented API; the FCA's structured
FS Register API requires separate registration/keys (`needs_separate_subscription`).

| LDH id | LDH name | LDH status @ check | Our status | Our tool(s) | Notes / rejection reason |
|---|---|---|---|---|---|
| UK/Legislation | UK Legislation (legislation.gov.uk) | complete | shipped | `gb_search`, `gb_get_act`, `gb_get_text`, `gb_recent_legislation` | shipped v0.1.0 (feature-001), 2026-06 |
| UK/LegislationGovUK | UK Legislation | complete | shipped | `gb_search`, `gb_get_act`, `gb_get_text`, `gb_recent_legislation` | `duplicate` of UK/Legislation - same upstream, same tools |
| UK/CaseLaw | UK Case Law (National Archives) | complete | shipped | `gb_search_case_law`, `gb_get_case` | shipped v0.2.0 (feature-002), 2026-07-06 |
| UK/FindCaseLaw | UK Find Case Law (National Archives) | complete | shipped | `gb_search_case_law`, `gb_get_case` | `duplicate` of UK/CaseLaw - same upstream, same tools |
| UK/JCPC-Crown | Judicial Committee of the Privy Council | complete | shipped | `gb_search_case_law`, `gb_get_case` | covered by existing Find Case Law tools, `court=ukpc` confirmed live 2026-07-07 (~355 docs, 71 feed pages x 5) |
| UK/ET | UK Employment Tribunals | complete | shipped | `gb_search_govuk`, `gb_get_govuk_content` | shipped feature-003, 2026-07-07; 132,162 docs verified (+ EAT 2,571 as `employment_appeal_tribunal_decision`) |
| UK/HMRC | UK HMRC Tax Manuals | complete | shipped | `gb_search_govuk`, `gb_get_govuk_content` | shipped feature-003, 2026-07-07; 85,315 manual sections + 251 manuals verified |
| UK/HMRC-Manuals | HMRC Tax Guidance Manuals | complete | shipped | `gb_search_govuk`, `gb_get_govuk_content` | `duplicate` of UK/HMRC - same gov.uk document types |
| UK/CMA | UK Competition and Markets Authority | complete | shipped | `gb_search_govuk`, `gb_get_govuk_content` | shipped feature-003, 2026-07-07; 2,565 `cma_case` docs verified |
| UK/FTT-Tax | UK First-tier Tribunal - Tax Chamber | complete | shipped | `gb_search_govuk`, `gb_get_govuk_content` | shipped feature-003, 2026-07-07; 1,414 `tax_tribunal_decision` docs verified |
| UK/IAC | UK Immigration and Asylum Chamber | complete | rejected | - | `bot_protection` - not on gov.uk (404); tribunalsdecisions.service.gov.uk returns 406 "Agent not allowed" on machine endpoints, probed 2026-07-07 |
| UK/ICO | UK Information Commissioner (ICO) | complete | rejected | - | `no_machine_readable_api` - HTML facet listing only, no JSON/Atom/total field; screen-scrape breaks the citation contract, probed 2026-07-07 |
| UK/FCA | UK Financial Conduct Authority (FCA) | complete | rejected | - | `undocumented_third_party_search_backend` (internal Funnelback cloud) + FS Register `needs_separate_subscription`, probed 2026-07-07 |
| UK/HMRC-Excise | UK HMRC Excise Decisions | complete | todo | - | likely reachable via gov.uk Search API org filter, not yet evaluated |
| UK/CAT | UK Competition Appeal Tribunal | complete | todo | - | catribunal.org.uk, separate host, not yet evaluated, priority p2 |
| UK/PHSO | UK Parliamentary and Health Service Ombudsman | complete | todo | - | decisions.ombudsman.org.uk, not yet evaluated, priority p2 |
| UK/Ofcom | UK Communications Regulator (Ofcom) | complete | todo | - | not yet evaluated, priority p2 |
| UK/ASA | UK Advertising Standards Authority | complete | todo | - | not yet evaluated, priority p2 |

## Status vocabulary

- `shipped` - live in this repo, has at least one MCP tool, tested and published.
- `rejected` - scouted, deliberately NOT built. `Notes` column MUST give a reason, using LDH's own
  taxonomy where it applies (`bot_protection`, `captcha_required`, `geo_restricted`,
  `requires_bigquery_credentials`, `duplicate`, `no_full_text_access`, `waf_blocked`,
  `spa_requires_browser`) or a MateMatic-specific one (`needs_separate_subscription`,
  `unreliable_exact_match`, `no_machine_readable_api`,
  `undocumented_third_party_search_backend`).
- `todo` - LDH has it as `complete`, we have not evaluated it yet. Prime candidate for the next
  widen-round, sorted by LDH `priority` (1 = highest) then by expected legal weight.

## Not on this list

Anything NOT in this table has simply not been checked yet against this country's LDH sources -
absence is not a claim of non-existence. Re-run `eu-legal-mcp/gap_scan.py --country GB` to find
genuinely new entries (LDH lists 48 UK sources, 40 `complete`, as of 2026-07-07).
