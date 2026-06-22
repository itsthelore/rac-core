"""Traceability coverage report tests (v0.24, WS-F).

Each typed gap class is exercised on a built corpus, plus the clean case, the
JSON contract, and the advisory exit code (coverage never fails a build).
"""

from __future__ import annotations

import json
from pathlib import Path

from rac.cli import main
from rac.services.coverage import (
    GAP_UNAPPLIED,
    GAP_UNSCHEDULED,
    GAP_UNSCOPED,
    analyze_coverage,
)

REQ_BODY = "## Problem\n\nNeeded.\n\n## Requirements\n\n- [REQ-001] The system MUST do X.\n"
DEC_BODY = (
    "## Status\n\nAccepted\n\n## Category\n\nArchitecture\n\n## Context\n\nC.\n\n"
    "## Decision\n\nD.\n\n## Consequences\n\nX.\n"
)
RDM_BODY = "## Outcomes\n\n- An outcome.\n\n## Initiatives\n\n- An initiative.\n"


def _write(base: Path, name: str, ident: str, atype: str, body: str, related: str = "") -> None:
    (base / name).write_text(
        f"---\nschema_version: 1\nid: {ident}\ntype: {atype}\n---\n# {ident}\n\n{body}{related}",
        encoding="utf-8",
    )


def _related(section: str, *ids: str) -> str:
    return f"\n## {section}\n\n" + "".join(f"- {i}\n" for i in ids)


def test_unscheduled_requirement_flagged(tmp_path):
    # A requirement no roadmap references is unscheduled.
    _write(tmp_path, "req.md", "RAC-TCVREQ000001", "requirement", REQ_BODY)
    report = analyze_coverage(str(tmp_path))
    assert [(g.type, g.gap) for g in report.gaps] == [("requirement", GAP_UNSCHEDULED)]


def test_scheduled_requirement_not_flagged(tmp_path):
    # A roadmap that references the requirement clears the unscheduled gap...
    _write(tmp_path, "req.md", "RAC-TCVREQ000001", "requirement", REQ_BODY)
    _write(
        tmp_path,
        "rdm.md",
        "RAC-TCVRDM000001",
        "roadmap",
        RDM_BODY,
        _related("Related Requirements", "RAC-TCVREQ000001"),
    )
    report = analyze_coverage(str(tmp_path))
    # ...and that roadmap is itself scoped (it references a requirement), so no gaps.
    assert report.gaps == []


def test_unapplied_decision_flagged(tmp_path):
    _write(tmp_path, "dec.md", "RAC-TCVDEC000001", "decision", DEC_BODY)
    report = analyze_coverage(str(tmp_path))
    assert [(g.type, g.gap) for g in report.gaps] == [("decision", GAP_UNAPPLIED)]


def test_decision_applied_by_requirement_not_flagged(tmp_path):
    _write(tmp_path, "dec.md", "RAC-TCVDEC000001", "decision", DEC_BODY)
    _write(
        tmp_path,
        "req.md",
        "RAC-TCVREQ000001",
        "requirement",
        REQ_BODY,
        _related("Related Decisions", "RAC-TCVDEC000001"),
    )
    report = analyze_coverage(str(tmp_path))
    # The decision is applied; the requirement is still unscheduled.
    assert [(g.type, g.gap) for g in report.gaps] == [("requirement", GAP_UNSCHEDULED)]


def test_unscoped_roadmap_flagged(tmp_path):
    _write(tmp_path, "rdm.md", "RAC-TCVRDM000001", "roadmap", RDM_BODY)
    report = analyze_coverage(str(tmp_path))
    assert [(g.type, g.gap) for g in report.gaps] == [("roadmap", GAP_UNSCOPED)]


def test_gaps_ordered_by_class_then_path(tmp_path):
    _write(tmp_path, "rdm.md", "RAC-TCVRDM000001", "roadmap", RDM_BODY)
    _write(tmp_path, "dec.md", "RAC-TCVDEC000001", "decision", DEC_BODY)
    _write(tmp_path, "req.md", "RAC-TCVREQ000001", "requirement", REQ_BODY)
    report = analyze_coverage(str(tmp_path))
    # unscheduled, then unapplied, then unscoped (REQ-003).
    assert [g.gap for g in report.gaps] == [GAP_UNSCHEDULED, GAP_UNAPPLIED, GAP_UNSCOPED]


def test_json_contract_and_summary(tmp_path):
    _write(tmp_path, "req.md", "RAC-TCVREQ000001", "requirement", REQ_BODY)
    report = analyze_coverage(str(tmp_path))
    data = report.to_dict()
    assert data["schema_version"] == "1"
    assert data["summary"] == {
        GAP_UNSCHEDULED: 1,
        GAP_UNAPPLIED: 0,
        GAP_UNSCOPED: 0,
        "total": 1,
    }
    gap = data["gaps"][0]
    assert set(gap) == {"path", "id", "type", "gap", "missing"}


def test_cli_coverage_is_advisory_exit_zero(tmp_path, capsys):
    _write(tmp_path, "req.md", "RAC-TCVREQ000001", "requirement", REQ_BODY)
    rc = main(["coverage", str(tmp_path)])
    assert rc == 0  # advisory, never a build failure (REQ-005)
    assert "Unscheduled requirements" in capsys.readouterr().out


def test_cli_coverage_json(tmp_path, capsys):
    _write(tmp_path, "req.md", "RAC-TCVREQ000001", "requirement", REQ_BODY)
    rc = main(["coverage", str(tmp_path), "--json"])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["summary"]["total"] == 1


def test_clean_corpus_has_no_gaps(tmp_path, capsys):
    # A roadmap scoping a requirement, the requirement scheduled, a decision applied.
    _write(
        tmp_path,
        "rdm.md",
        "RAC-TCVRDM000001",
        "roadmap",
        RDM_BODY,
        _related("Related Requirements", "RAC-TCVREQ000001"),
    )
    _write(
        tmp_path,
        "req.md",
        "RAC-TCVREQ000001",
        "requirement",
        REQ_BODY,
        _related("Related Decisions", "RAC-TCVDEC000001"),
    )
    _write(tmp_path, "dec.md", "RAC-TCVDEC000001", "decision", DEC_BODY)
    report = analyze_coverage(str(tmp_path))
    assert report.gaps == []
