"""Tests for Layer-3 relationship-graph integrity (ADR-055, ADR-051).

Covers the new graph checks — range (wrong target type), acyclicity (supersedes
cycles), and the generalized all-type status-consistency rule — plus the
relationship-type registry and the validation_status the portfolio summary
exposes to the MCP get_summary tool.
"""

from __future__ import annotations

from rac.core.relationship_types import REGISTRY, edge_spec
from rac.services.portfolio import build_portfolio_summary
from rac.services.relationships import (
    ISSUE_RELATIONSHIP_CYCLE,
    ISSUE_TARGET_SUPERSEDED,
    ISSUE_TARGET_TYPE_MISMATCH,
    validate_relationships,
)


def _write(path, text):
    path.write_text(text, encoding="utf-8")


def _req(title, extra=""):
    return f"# {title}\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] do the thing\n{extra}\n"


def _dec(title, status="Accepted", extra=""):
    return (
        f"# {title}\n\n## Context\n\nc\n\n## Decision\n\nd\n\n"
        f"## Consequences\n\nx\n\n## Status\n\n{status}\n{extra}\n"
    )


def codes(report):
    return {i.code for i in report.issues}


# --- registry ----------------------------------------------------------------


def test_registry_declares_built_in_edges():
    assert set(REGISTRY) == {
        "related_requirements",
        "related_decisions",
        "related_roadmaps",
        "related_prompts",
        "related_designs",
        "supersedes",
    }
    supersedes = edge_spec("supersedes")
    assert supersedes is not None
    assert supersedes.directional and supersedes.acyclic
    assert supersedes.forbids_target_status is False  # the exemption is data-driven
    assert edge_spec("related_decisions").range == ("decision",)
    assert edge_spec("related_decisions").forbids_target_status is True


# --- range -------------------------------------------------------------------


def test_range_mismatch_is_flagged(tmp_path):
    # A requirement declares ## Related Decisions but points at another requirement.
    _write(tmp_path / "target.md", _req("Target Requirement"))
    _write(tmp_path / "source.md", _req("Source", "\n## Related Decisions\n\n- target\n"))
    report = validate_relationships(str(tmp_path))
    assert ISSUE_TARGET_TYPE_MISMATCH in codes(report)
    issue = next(i for i in report.issues if i.code == ISSUE_TARGET_TYPE_MISMATCH)
    assert issue.relationship == "related_decisions"
    assert issue.target == "target"


def test_range_match_passes(tmp_path):
    _write(tmp_path / "d.md", _dec("A Decision"))
    _write(tmp_path / "source.md", _req("Source", "\n## Related Decisions\n\n- d\n"))
    report = validate_relationships(str(tmp_path))
    assert ISSUE_TARGET_TYPE_MISMATCH not in codes(report)


def test_range_exempts_untyped_target(tmp_path):
    # An untyped document target (ADR-010) is not a range violation.
    _write(tmp_path / "notes.md", "# Loose Notes\n\njust prose, no schema\n")
    _write(tmp_path / "source.md", _req("Source", "\n## Related Decisions\n\n- notes\n"))
    report = validate_relationships(str(tmp_path))
    assert ISSUE_TARGET_TYPE_MISMATCH not in codes(report)


# --- acyclicity --------------------------------------------------------------


def test_supersedes_cycle_is_flagged(tmp_path):
    _write(tmp_path / "a.md", _dec("A", extra="\n## Supersedes\n\n- b\n"))
    _write(tmp_path / "b.md", _dec("B", extra="\n## Supersedes\n\n- a\n"))
    report = validate_relationships(str(tmp_path))
    assert ISSUE_RELATIONSHIP_CYCLE in codes(report)
    cycle = next(i for i in report.issues if i.code == ISSUE_RELATIONSHIP_CYCLE)
    assert cycle.relationship == "supersedes"
    assert sorted(p.rsplit("/", 1)[-1] for p in cycle.paths) == ["a.md", "b.md"]


def test_acyclic_supersedes_chain_passes(tmp_path):
    # a supersedes b supersedes c — a chain, not a cycle.
    _write(tmp_path / "a.md", _dec("A", extra="\n## Supersedes\n\n- b\n"))
    _write(tmp_path / "b.md", _dec("B", status="Superseded", extra="\n## Supersedes\n\n- c\n"))
    _write(tmp_path / "c.md", _dec("C", status="Superseded"))
    report = validate_relationships(str(tmp_path))
    assert ISSUE_RELATIONSHIP_CYCLE not in codes(report)


# --- generalized status-consistency (ADR-051) --------------------------------


def test_live_requirement_referencing_retired_requirement_fails(tmp_path):
    _write(tmp_path / "old.md", _req("Old", "\n## Status\n\nSuperseded\n"))
    _write(tmp_path / "live.md", _req("Live", "\n## Related Requirements\n\n- old\n"))
    report = validate_relationships(str(tmp_path))
    assert ISSUE_TARGET_SUPERSEDED in codes(report)


def test_retired_source_is_exempt(tmp_path):
    # A retired artifact's own outbound reference is a historical chain, not a fault.
    _write(tmp_path / "old.md", _req("Old", "\n## Status\n\nSuperseded\n"))
    _write(
        tmp_path / "older.md",
        _req("Older", "\n## Status\n\nSuperseded\n\n## Related Requirements\n\n- old\n"),
    )
    report = validate_relationships(str(tmp_path))
    assert ISSUE_TARGET_SUPERSEDED not in codes(report)


def test_supersedes_to_retired_decision_is_exempt(tmp_path):
    # The replacing decision legitimately points at the one it retires.
    _write(tmp_path / "old.md", _dec("Old", status="Superseded"))
    _write(tmp_path / "new.md", _dec("New", extra="\n## Supersedes\n\n- old\n"))
    report = validate_relationships(str(tmp_path))
    assert ISSUE_TARGET_SUPERSEDED not in codes(report)


# --- validation_status in the summary (MCP get_summary) ----------------------


def test_summary_reports_validation_status_ok(tmp_path):
    _write(tmp_path / "d.md", _dec("A Decision"))
    payload = build_portfolio_summary(str(tmp_path)).to_dict()
    assert payload["validation_status"] == {
        "artifacts_ok": True,
        "relationships_ok": True,
        "ok": True,
    }


def test_summary_reports_relationship_failure(tmp_path):
    _write(tmp_path / "source.md", _req("Source", "\n## Related Decisions\n\n- nope\n"))
    payload = build_portfolio_summary(str(tmp_path)).to_dict()
    assert payload["validation_status"]["relationships_ok"] is False
    assert payload["validation_status"]["ok"] is False
