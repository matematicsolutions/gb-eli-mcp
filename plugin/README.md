# gb-eli-mcp - Claude plugin

UK law with verifiable citations, as a Claude plugin. It runs the
[gb-eli-mcp](https://github.com/matematicsolutions/gb-eli-mcp) MCP server, version 0.5.3
from PyPI. `server/uv.lock` pins that package and every dependency with hashes, and the
plugin starts it with `uv run --frozen`, so it runs exactly what was reviewed. Every
answer carries the official source, so a citation can be checked instead of trusted.

What it covers: UK legislation from legislation.gov.uk (search, an act's metadata and text, recent legislation), judgments from Find Case Law at The National Archives (search and full judgment), and GOV.UK content through its search and content APIs (tribunal decisions, HMRC manuals, CMA cases). The full tool list is in the
[main README](https://github.com/matematicsolutions/gb-eli-mcp#readme).

## Requirements

Claude Code or the Claude desktop app, and [uv](https://docs.astral.sh/uv/) on your
machine (it installs the locked packages on first start and runs the server).

## Install

```
/plugin marketplace add matematicsolutions/gb-eli-mcp
/plugin install gb-eli-mcp@gb-eli-mcp
```

## Data

The server runs on your machine. Each tool call sends your query to the official UK source it names (legislation.gov.uk, Find Case Law at caselaw.nationalarchives.gov.uk, or GOV.UK)
and to nothing else; nothing goes to MateMatic. Your query and the results also pass
through whatever model you use, the same way as any other message.

The standalone server can fetch a small configuration file (updated source addresses) from
this repository's GitHub Releases on first use. The plugin turns that off
(`GB_ELI_RUNTIME_URL` set to empty in `plugin.json`), so it runs only the reviewed code with
its built-in source addresses and makes no request other than the tool calls above.

Two things are written locally, in your home directory:

- a response cache (`~/.matematic/cache/gb-eli`), so a repeated lookup does not hit
  the source again. Court decisions are public records and can name the parties.
- an audit log (`~/.matematic/audit/gb-eli-mcp.jsonl`), one line per tool call: the
  tool name, a SHA-256 hash of the input (not the input itself), result size, time
  and status.

Delete either folder at any time; `GB_ELI_CACHE_DIR` and `GB_ELI_AUDIT_DIR` move them.

## Licence

Apache-2.0, see the repository's [LICENSE](https://github.com/matematicsolutions/gb-eli-mcp/blob/main/LICENSE).
