"""Tests for generalized lifecycle status validation (ADR-051).

Status is an optional, validated `## Status` body section on every artifact type.
A present value outside the type's enum is an error (`invalid-<type>-status`); a
missing section is fine. The decision code `invalid-decision-status` is unchanged
(ADR-007).
"""

from __future__ import annotations

from rac.core.markdown import parse
from rac.core.validation import validate

REQUIREMENT = "# R\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] do it\n\n## Status\n\n{s}\n"
ROADMAP = "# R\n\n## Outcomes\n\no\n\n## Initiatives\n\ni\n\n## Status\n\n{s}\n"
PROMPT = (
    "# P\n\n## Objective\n\no\n\n## Input\n\ni\n\n## Instructions\n\nx\n\n"
    "## Output\n\nout\n\n## Status\n\n{s}\n"
)
DESIGN = (
    "# D\n\n## Context\n\nc\n\n## User Need\n\nu\n\n## Design\n\nd\n\n"
    "## Constraints\n\nk\n\n## Status\n\n{s}\n"
)


def codes(text):
    return {i.code for i in validate(parse(text))}


def test_valid_status_passes_per_type():
    assert "invalid-requirement-status" not in codes(REQUIREMENT.format(s="Accepted"))
    assert "invalid-roadmap-status" not in codes(ROADMAP.format(s="Planned"))
    assert "invalid-prompt-status" not in codes(PROMPT.format(s="Active"))
    assert "invalid-design-status" not in codes(DESIGN.format(s="Superseded"))


def test_out_of_enum_status_fails_per_type():
    # roadmap has no Accepted; prompt has no Proposed — each is out of enum.
    assert "invalid-requirement-status" in codes(REQUIREMENT.format(s="Done"))
    assert "invalid-roadmap-status" in codes(ROADMAP.format(s="Accepted"))
    assert "invalid-prompt-status" in codes(PROMPT.format(s="Proposed"))
    assert "invalid-design-status" in codes(DESIGN.format(s="Shipped"))


def test_decision_status_code_unchanged():
    decision = (
        "# D\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nx\n\n## Status\n\nBogus\n"
    )
    assert "invalid-decision-status" in codes(decision)


def test_missing_status_is_optional():
    no_status = "# R\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] do it\n"
    assert not any(c.endswith("-status") for c in codes(no_status))
