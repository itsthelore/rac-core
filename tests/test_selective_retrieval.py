"""Selective on-demand retrieval by default (lean-context-delivery Init 2).

The default retrieval path returns the *relevant* artifacts for a query — never
the whole corpus — so an agent receives small, scoped payloads by construction,
the antidote to context rot. Bulk, whole-corpus delivery is an explicit action
(`rac export`), not a retrieval default (REQ-001, REQ-004). Selectivity is by
scoping, not by lossy compression (ADR-066).
"""

from __future__ import annotations

import asyncio
import json

from conftest import fixture_path

from rac.mcp.server import build_server
from rac.services.index import build_repository_index
from rac.services.resolve import find_artifacts

CORPUS = fixture_path("mcp", "corpus")
DECISION = "RAC-MCPDEC000001"


def _total_artifacts() -> int:
    return len([e for e in build_repository_index(CORPUS).artifacts if e.type != "unknown"])


def _call(tool: str, args: dict) -> str:
    async def go() -> str:
        contents, _ = await build_server(CORPUS).call_tool(tool, args)
        return contents[0].text

    return asyncio.run(go())


def test_cli_find_returns_a_relevant_subset_not_the_whole_corpus():
    total = _total_artifacts()
    assert total >= 3  # a corpus big enough for "subset" to mean something
    result = find_artifacts(CORPUS, "messaging")
    assert 0 < result.match_count < total


def test_mcp_search_is_selective_by_default():
    total = _total_artifacts()
    payload = json.loads(_call("search_artifacts", {"query": "messaging"}))
    assert 0 < payload["match_count"] < total


def test_lookup_returns_one_artifact_not_a_dump():
    # get_artifact is a scoped, on-demand lookup: one artifact by id, never the
    # corpus. The response is a single object keyed to the requested id.
    payload = json.loads(_call("get_artifact", {"id": DECISION}))
    assert payload["id"] == DECISION
    assert "error" not in payload


def test_no_retrieval_tool_returns_the_whole_corpus():
    # None of the retrieval surfaces hands back every artifact for a typical call:
    # search is a subset, lookup is one. The whole-corpus payload is only ever an
    # explicit `rac export`, never a default here.
    total = _total_artifacts()
    search = json.loads(_call("search_artifacts", {"query": "messaging"}))
    assert search["match_count"] < total
