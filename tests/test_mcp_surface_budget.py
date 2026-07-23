"""Measured MCP surface budget (lean-context-delivery Init 1, ADR-033 / ADR-066).

The agent-facing footprint is a regression-checked property, not silent drift: a
deterministic, offline token count of the five-tool surface (descriptions +
schemas) held under a stated budget, plus a per-call response ceiling over a
pinned fixture. No model, no network — the same input yields the same integer, so
a description or schema that inflates past the budget fails here rather than
quietly taxing every session.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from conftest import fixture_path

from asdecided.mcp.server import build_server
from asdecided.mcp.surface import (
    PER_CALL_BUDGET_TOKENS,
    STANDING_BUDGET_HARD_CAP,
    STANDING_BUDGET_TOKENS,
    approx_tokens,
    measure_surface,
)

# Two independent corpora: the standing surface (descriptions + schemas) must be
# identical over both, proving it is corpus-independent. The per-call basket runs
# over the grounding-demo corpus so the representative response is meaningful.
MCP_CORPUS = fixture_path("mcp", "corpus")
GUIDE_CORPUS = str(Path(__file__).parent.parent / "examples" / "guide")
DECISION = "GUIDE-KTW9YBDWDBFM"  # ADR-001, the grounding decision


def _measure(root: str):
    return asyncio.run(measure_surface(build_server(root)))


def _response(root: str, tool: str, args: dict) -> str:
    async def call() -> str:
        contents, _ = await build_server(root).call_tool(tool, args)
        return contents[0].text

    return asyncio.run(call())


# --- the tokenisation rule (REQ-002) -----------------------------------------


def test_token_rule_is_the_stated_deterministic_count():
    # Word runs and standalone punctuation each count once; whitespace is skipped.
    assert approx_tokens("") == 0
    assert approx_tokens("hello world") == 2
    assert approx_tokens("a, b.") == 4  # a , b .
    # Underscores split words (they are punctuation under the rule) — pinned so
    # the behaviour is explicit, since tool names carry them.
    assert approx_tokens("get_artifact") == 3  # get _ artifact


# --- standing surface budget (REQ-001, REQ-003, REQ-004) ---------------------


def test_standing_surface_is_within_budget():
    measurement = _measure(MCP_CORPUS)
    assert measurement.standing_tokens <= STANDING_BUDGET_TOKENS, (
        f"MCP standing surface is {measurement.standing_tokens} tokens, over the "
        f"{STANDING_BUDGET_TOKENS} budget. Trim a tool description or schema, or "
        f"raise the budget (with justification, up to {STANDING_BUDGET_HARD_CAP}) "
        "beside the constant in rac/mcp/surface.py."
    )


def test_surface_is_the_five_tool_surface_unchanged():
    # The measurement counts the served surface; it adds no tool and removes none.
    measurement = _measure(MCP_CORPUS)
    assert len(measurement.tools) == 5
    assert {t.name for t in measurement.tools} == {
        "get_summary",
        "search_artifacts",
        "get_artifact",
        "get_related",
        "find_decisions",
    }


def test_standing_surface_is_corpus_independent():
    # Descriptions + schemas do not depend on the corpus, so the standing number
    # is a stable property of the server, not of any one repository.
    assert _measure(MCP_CORPUS).standing_tokens == _measure(GUIDE_CORPUS).standing_tokens


def test_measurement_is_deterministic():
    # Same input, same integer — no model, no network (REQ-002).
    assert _measure(MCP_CORPUS).standing_tokens == _measure(MCP_CORPUS).standing_tokens


def test_budget_stays_within_its_hard_cap():
    # The budget may be raised with review, but never silently past the cap: going
    # above 1250 is a deliberate change to the cap itself, not a quiet bump.
    assert STANDING_BUDGET_TOKENS <= STANDING_BUDGET_HARD_CAP


# --- per-call response budget (REQ-005) --------------------------------------


def test_typical_responses_are_within_the_per_call_budget():
    # A representative search page and a representative get_artifact payload over
    # the pinned fixture stay under the per-call ceiling. This catches
    # serialization field-bloat below ADR-033's serve-time truncation.
    search = _response(GUIDE_CORPUS, "search_artifacts", {"query": "delete user"})
    artifact = _response(GUIDE_CORPUS, "get_artifact", {"id": DECISION})
    assert approx_tokens(search) <= PER_CALL_BUDGET_TOKENS
    assert approx_tokens(artifact) <= PER_CALL_BUDGET_TOKENS
