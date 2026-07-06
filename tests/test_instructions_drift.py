"""Drift test - INSTRUCTIONS consistent with registered tools and ErrorCode.

Cherry-picked from dograh-hq/dograh v1.31.0 (BSD-2) via mcp-eu-compliance v0.2.0.
Adapted for FastMCP Python.

Fails if:
  1. A tool name in INSTRUCTIONS (backtick) is not registered in mcp
  2. An ErrorCode in GbEliError.VALID_CODES is not documented in INSTRUCTIONS
  3. A tool references a GbEliError code not in VALID_CODES (heuristic)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gb_eli_mcp.server import INSTRUCTIONS, GbEliError, mcp

SRC = (Path(__file__).parent.parent / "src" / "gb_eli_mcp" / "server.py").read_text(
    encoding="utf-8"
)


def _registered_tool_names() -> set[str]:
    """Names of all tools registered in FastMCP."""
    if hasattr(mcp, "_tool_manager"):
        tools_dict = getattr(mcp._tool_manager, "_tools", {})
        if tools_dict:
            return set(tools_dict.keys())
    return set(re.findall(r"@mcp\.tool\([^)]*\)\s+async def (\w+)", SRC))


def _referenced_tool_names_in_instructions() -> set[str]:
    """Tool names in INSTRUCTIONS (backtick code spans `gb_xxx`)."""
    skip = {"isError", "true", "false", "html", "xml", "pdf", "struct"}
    out: set[str] = set()
    for m in re.finditer(r"`([a-z][a-z0-9_]{3,})`", INSTRUCTIONS):
        token = m.group(1)
        if token in skip:
            continue
        if "_" in token:  # tool names are snake_case with _
            out.add(token)
    return out


def test_instructions_only_reference_registered_tools():
    """Every tool name in INSTRUCTIONS must be registered.

    Response fields (eli_uri, source_url, ...) are not gb_-prefixed, so they are
    excluded by the gb_ filter below.
    """
    registered = _registered_tool_names()
    referenced = _referenced_tool_names_in_instructions()
    referenced_tools = {r for r in referenced if r.startswith("gb_")}
    orphan = referenced_tools - registered
    assert not orphan, (
        f"INSTRUCTIONS reference tools not in mcp: {orphan}. "
        f"Registered: {sorted(registered)}."
    )


def test_error_codes_documented_in_instructions():
    """Every ErrorCode in VALID_CODES must appear in INSTRUCTIONS."""
    undocumented = set()
    for code in GbEliError.VALID_CODES:
        if not re.search(r"\b" + re.escape(code) + r"\b", INSTRUCTIONS):
            undocumented.add(code)
    assert not undocumented, (
        f"ErrorCode in VALID_CODES not documented in INSTRUCTIONS: {undocumented}."
    )


def test_raised_error_codes_in_valid_codes():
    """Every GbEliError(<code>, ...) in the code must be in VALID_CODES."""
    raised = set(re.findall(r'GbEliError\(\s*"(\w+)"\s*,', SRC))
    invalid = raised - GbEliError.VALID_CODES
    assert not invalid, (
        f"GbEliError uses codes not in VALID_CODES: {invalid}. "
        f"VALID_CODES: {sorted(GbEliError.VALID_CODES)}"
    )


def test_gb_eli_error_format():
    """GbEliError formats as '[code] message' for the LLM."""
    err = GbEliError("invalid_arg", "Bad reference: 'foo'")
    assert str(err).startswith("[invalid_arg] ")
    assert "Bad reference" in str(err)


def test_gb_eli_error_rejects_unknown_code():
    """GbEliError with an unknown code raises in the constructor - guards against drift."""
    with pytest.raises(ValueError, match="Unknown GbEliError code"):
        GbEliError("nonexistent_code", "x")
