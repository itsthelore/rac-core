"""Characterization pins for MCP tool response payloads (rebuild).

The MCP server (ADR-029 ff.) is a first-class delivery surface: agents consume
the exact text payload each tool returns. Existing MCP tests assert structural
shape or parity with a service, but none byte-pin the serialized tool output,
and ``get_summary`` / ``find_decisions`` (path mode) deliberately bypass the
derived-index cache (ADR-099) — so a rebuild of either the serializer or the
cache path could shift bytes without a golden noticing.

These tests call the in-process server the way the suite already does (see
``tests/test_derived_cache.py``), against the static ``tests/fixtures/resolve``
corpus, and compare the returned text byte-for-byte against a committed expected
file. The corpus is static Markdown, so payloads are deterministic without
controlling git state.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from rac.mcp.server import build_server

REPO_ROOT = Path(__file__).parent.parent
EXPECTED_DIR = Path(__file__).parent / "fixtures" / "characterization"
CORPUS = "tests/fixtures/resolve"


def _tool_text(server, name, args) -> str:
    content, _structured = asyncio.run(server.call_tool(name, args))
    return content[0].text


# (expected-file stem, tool name, args)
CASES = [
    ("mcp_get_summary", "get_summary", {}),
    ("mcp_find_decisions_topic", "find_decisions", {"topic": "markdown"}),
    (
        "mcp_find_decisions_path",
        "find_decisions",
        {"path": "tests/fixtures/resolve/v0-canonical-format.md"},
    ),
    ("mcp_get_related", "get_related", {"id": "RAC-01JY4M8X2QZ7"}),
    ("mcp_get_artifact", "get_artifact", {"id": "RAC-01JY4M8X2QZ7"}),
]


@pytest.mark.parametrize("stem,tool,args", CASES, ids=[c[0] for c in CASES])
def test_mcp_tool_payload_is_byte_stable(stem, tool, args, monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    server = build_server(CORPUS)
    text = _tool_text(server, tool, args)
    expected = (EXPECTED_DIR / f"{stem}.txt").read_text(encoding="utf-8")
    assert text == expected, f"MCP `{tool}` payload drifted from the frozen pin."


def test_find_decisions_topic_and_path_modes_have_distinct_envelopes(monkeypatch):
    # Two distinct response shapes hang off one tool name: topic mode carries a
    # `matches`/`filter` search envelope, path mode carries `in_repository`/
    # `decisions`. Pin that the discriminating keys stay put.
    monkeypatch.chdir(REPO_ROOT)
    server = build_server(CORPUS)
    import json

    topic = json.loads(_tool_text(server, "find_decisions", {"topic": "markdown"}))
    path = json.loads(
        _tool_text(
            server,
            "find_decisions",
            {"path": "tests/fixtures/resolve/v0-canonical-format.md"},
        )
    )
    assert "matches" in topic and "filter" in topic
    assert "in_repository" in path and "decisions" in path
