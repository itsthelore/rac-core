"""Mentioned-but-unlinked reference detection battery (link-suggestions, ADR-082).

Pins the detector contract: a body reference to another artifact with no declared
`## Related` edge becomes one advisory suggestion; declared edges, self-references,
fenced code, and repeated mentions never produce spurious findings; the suggested
line uses the corpus-idiomatic ref form; and output is deterministic.
"""

from __future__ import annotations

from pathlib import Path

from rac.services.links import detect_unlinked_references

DECISION = """\
---
schema_version: 1
id: {id}
type: decision
---
# {title}

## Status

Accepted

## Context

{context}

## Decision

Do it.

## Consequences

Fine.
"""

REQUIREMENT = """\
---
schema_version: 1
id: {id}
type: requirement
---
# {title}

## Problem

A problem worth solving.

## Requirements

- [REQ-001] The system MUST do the thing.
{related}
"""


def _decision(root: Path, name: str, aid: str, *, context: str = "Background.") -> None:
    (root / f"{name}.md").write_text(
        DECISION.format(id=aid, title=name.title(), context=context), encoding="utf-8"
    )


def _requirement(
    root: Path, name: str, aid: str, *, problem_ref: str = "", related: list[str] | None = None
) -> None:
    rel = ""
    if related:
        rel = "\n## Related Decisions\n\n" + "\n".join(f"- {r}" for r in related) + "\n"
    body = REQUIREMENT.format(id=aid, title=name.title(), related=rel)
    if problem_ref:
        body = body.replace(
            "A problem worth solving.", f"A problem worth solving; see {problem_ref}."
        )
    (root / f"{name}.md").write_text(body, encoding="utf-8")


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    root.mkdir()
    return root


def test_body_mention_without_edge_is_detected(tmp_path):
    root = _corpus(tmp_path)
    _decision(root, "adr-001-alpha", "RAC-AAAAAAAAAAAA", context="This builds on adr-002.")
    _decision(root, "adr-002-beta", "RAC-BBBBBBBBBBBB")
    refs = detect_unlinked_references(str(root))
    assert len(refs) == 1
    found = refs[0]
    assert found.source_path.endswith("adr-001-alpha.md")
    assert found.target_path.endswith("adr-002-beta.md")
    assert found.matched_token == "adr-002"
    assert found.related_section == "Related Decisions"
    assert found.suggested_line == "- adr-002"


def test_declared_edge_is_not_flagged(tmp_path):
    root = _corpus(tmp_path)
    _decision(root, "adr-002-beta", "RAC-BBBBBBBBBBBB")
    # The requirement both mentions the decision in prose AND declares the edge.
    _requirement(
        root,
        "requirement-gamma",
        "RAC-GGGGGGGGGGGG",
        problem_ref="adr-002",
        related=["adr-002"],
    )
    assert detect_unlinked_references(str(root)) == []


def test_self_reference_is_ignored(tmp_path):
    root = _corpus(tmp_path)
    # adr-001 names its own id and filename ref in its body.
    _decision(
        root,
        "adr-001-alpha",
        "RAC-AAAAAAAAAAAA",
        context="As established in adr-001 (RAC-AAAAAAAAAAAA), this holds.",
    )
    assert detect_unlinked_references(str(root)) == []


def test_fenced_code_is_excluded(tmp_path):
    root = _corpus(tmp_path)
    _decision(root, "adr-002-beta", "RAC-BBBBBBBBBBBB")
    # The only mention of adr-002 lives inside a fenced code block.
    fenced = "An example follows:\n\n```\nrac resolve adr-002\n```\n\nNo prose mention here."
    _decision(root, "adr-001-alpha", "RAC-AAAAAAAAAAAA", context=fenced)
    assert detect_unlinked_references(str(root)) == []


def test_one_finding_per_pair(tmp_path):
    root = _corpus(tmp_path)
    _decision(root, "adr-002-beta", "RAC-BBBBBBBBBBBB")
    _decision(
        root,
        "adr-001-alpha",
        "RAC-AAAAAAAAAAAA",
        context="First adr-002 mention. Then adr-002 again, and RAC-BBBBBBBBBBBB once more.",
    )
    refs = detect_unlinked_references(str(root))
    assert len(refs) == 1
    assert refs[0].target_path.endswith("adr-002-beta.md")


def test_unresolvable_token_is_not_a_finding(tmp_path):
    root = _corpus(tmp_path)
    _decision(
        root,
        "adr-001-alpha",
        "RAC-AAAAAAAAAAAA",
        context="A normal sentence mentioning req-999 and some-other-slug.",
    )
    assert detect_unlinked_references(str(root)) == []


def test_suggested_ref_uses_stem_for_non_decision(tmp_path):
    root = _corpus(tmp_path)
    _requirement(root, "growth-target", "RAC-TTTTTTTTTTTT")
    _decision(
        root, "adr-001-alpha", "RAC-AAAAAAAAAAAA", context="This relates to growth-target work."
    )
    refs = detect_unlinked_references(str(root))
    assert len(refs) == 1
    assert refs[0].related_section == "Related Requirements"
    assert refs[0].suggested_line == "- growth-target"


def test_findings_sorted_by_source_then_target(tmp_path):
    root = _corpus(tmp_path)
    _decision(root, "adr-002-beta", "RAC-BBBBBBBBBBBB")
    _decision(root, "adr-003-gamma", "RAC-CCCCCCCCCCCC")
    _decision(
        root,
        "adr-001-alpha",
        "RAC-AAAAAAAAAAAA",
        context="References adr-003 first, then adr-002.",
    )
    refs = detect_unlinked_references(str(root))
    keys = [(r.source_path, r.target_id) for r in refs]
    assert keys == sorted(keys)
    # Sorted by target id, not document order: RAC-BBB... before RAC-CCC...
    assert [r.target_id for r in refs] == ["RAC-BBBBBBBBBBBB", "RAC-CCCCCCCCCCCC"]


def test_deterministic_across_runs(tmp_path):
    root = _corpus(tmp_path)
    _decision(root, "adr-002-beta", "RAC-BBBBBBBBBBBB")
    _decision(root, "adr-001-alpha", "RAC-AAAAAAAAAAAA", context="Builds on adr-002.")
    first = detect_unlinked_references(str(root))
    second = detect_unlinked_references(str(root))
    assert first == second
