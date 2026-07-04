"""Measured MCP surface budget (lean-context-delivery, Initiative 1).

A knowledge server justifies itself only if it stays lean; otherwise it becomes
the "context tax" it was meant to cure. ADR-033 records the instinct as a
response budget, but nothing measured the *standing* agent-facing footprint — the
tool descriptions and JSON schemas a client pays for every session — so drift was
invisible: a description edit or a new field could inflate the surface with no
signal.

This module measures that footprint deterministically and offline (ADR-066): no
model, no network. A fixed input yields a fixed integer via one stated
tokenisation rule, so the number is reproducible from the inputs alone and can be
held to a budget as a regression check (`tests/test_mcp_surface_budget.py`). It
counts the existing five-tool surface exactly as served — it adds no tool, removes
none, and compresses nothing (REQ-004).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# --- The stated tokenisation rule (REQ-002) ----------------------------------
#
# Word runs (alphanumeric) and each standalone non-space, non-alphanumeric
# character (punctuation) count as one token. Dependency-free and deterministic —
# reproducible from the input alone. A real model tokenizer (e.g. tiktoken) would
# tie the number to a model's vocabulary and add a dependency, against the lean,
# offline posture (ADR-066); the design accepts a faithful-enough proxy, and this
# is it. Underscores split words (they are punctuation here), which is fine: the
# rule only has to be fixed and stated, not match any one model.
_TOKEN = re.compile(r"[A-Za-z0-9]+|[^\sA-Za-z0-9]")


def approx_tokens(text: str) -> int:
    """The deterministic, offline token count of ``text`` (the stated rule)."""
    return len(_TOKEN.findall(text))


# --- Budgets (kept beside the check; a change here is reviewed with it) -------
#
# The enforced ceiling on the standing surface (descriptions + schemas), in
# tokens. Measured surface today is ~915; the budget holds it under 1000. Raising
# it is a reviewed edit that MUST carry justification, and it may not exceed the
# hard cap below without a deeper reconsideration (a test pins that the budget
# itself stays within the cap).
STANDING_BUDGET_TOKENS = 1000
# The absolute cap on the budget constant itself: the standing budget may be
# raised — with explicit approval and written justification — up to here, and
# never silently past it.
STANDING_BUDGET_HARD_CAP = 1250
# The per-call response ceiling over the pinned fixture basket, in tokens. It
# catches serialization field-bloat in a typical response that sits below
# ADR-033's serve-time truncation cap; the two are complementary (REQ-005).
PER_CALL_BUDGET_TOKENS = 1400


@dataclass(frozen=True)
class ToolCost:
    """One tool's standing token cost: its description and its JSON schema."""

    name: str
    description_tokens: int
    schema_tokens: int

    @property
    def total(self) -> int:
        return self.description_tokens + self.schema_tokens


@dataclass(frozen=True)
class SurfaceMeasurement:
    """The standing token cost of the served tool surface, per tool and summed."""

    tools: tuple[ToolCost, ...]

    @property
    def standing_tokens(self) -> int:
        return sum(t.total for t in self.tools)

    @property
    def description_tokens(self) -> int:
        return sum(t.description_tokens for t in self.tools)

    @property
    def schema_tokens(self) -> int:
        return sum(t.schema_tokens for t in self.tools)

    def to_dict(self) -> dict[str, Any]:
        return {
            "standing_tokens": self.standing_tokens,
            "description_tokens": self.description_tokens,
            "schema_tokens": self.schema_tokens,
            "budget": STANDING_BUDGET_TOKENS,
            "tools": [
                {"name": t.name, "description": t.description_tokens, "schema": t.schema_tokens}
                for t in self.tools
            ],
        }


async def measure_surface(server: Any) -> SurfaceMeasurement:
    """The standing token cost of ``server``'s tool surface (descriptions + schemas).

    Corpus-independent: it counts the served tool descriptions and their JSON
    schemas exactly as advertised to a client, over the stated tokenisation rule.
    Tools are sorted by name so the measurement is order-stable.
    """
    tools = await server.list_tools()
    costs = tuple(
        ToolCost(
            name=tool.name,
            description_tokens=approx_tokens(tool.description or ""),
            schema_tokens=approx_tokens(json.dumps(tool.inputSchema, sort_keys=True)),
        )
        for tool in sorted(tools, key=lambda t: t.name)
    )
    return SurfaceMeasurement(tools=costs)
