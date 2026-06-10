"""Tests for the v0.7.1 `rac relationships` command.

Repository-level relationship inspection (ADR-015): discovers the explicit
relationships declared across artifacts, counts individual references, and emits
deterministic human + JSON output. Read-only; no resolution, validation,
graphing, or inference (those are v0.7.2+).

Reuses the shared `fixtures/relationships/` artifacts and a dedicated
`fixtures/no_relationships/` directory for the empty-repository case.
"""

from __future__ import annotations

import json

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.services.relationships import (
    build_relationship_report,
    build_relationship_report_file,
)

# Reference counts (individual edges) over fixtures/relationships/, canonical order.
EXPECTED_COUNTS = {
    "related_requirements": 5,
    "related_decisions": 5,
    "related_roadmaps": 4,
    "related_prompts": 3,
    "related_designs": 4,
    "supersedes": 1,
}


# --- service layer -----------------------------------------------------------


def test_build_report_counts_individual_references():
    report = build_relationship_report(fixture_path("relationships"))
    assert report.total_files == 5
    assert report.artifacts_with_relationships == 5
    assert report.counts == EXPECTED_COUNTS
    assert report.relationship_count == 22
    assert report.relationship_count == sum(report.counts.values())


def test_build_report_file_single_artifact():
    path = fixture_path("relationships", "decision_with_links.md")
    report = build_relationship_report_file(path)
    assert report.total_files == 1
    assert report.recursive is False
    assert report.directory == path
    assert len(report.artifacts) == 1
    assert report.artifacts[0].type == "decision"


# --- human output (REQ-004 / REQ-005) ---------------------------------------


def test_human_summary(capsys):
    rc = main(["relationships", fixture_path("relationships")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Relationships" in out
    assert "Files Inspected: 5" in out
    assert "Artifacts With Relationships: 5" in out
    assert "Relationships Found: 22" in out
    assert "By Type:" in out
    assert "- Related Decisions: 5" in out
    assert "- Supersedes: 1" in out


def test_human_per_artifact_detail(capsys):
    rc = main(["relationships", fixture_path("relationships")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "requirement_with_links.md" in out
    assert "  Related Decisions:" in out
    assert "  - ADR-004" in out
    # Supersedes renders as a relationship in this command (unlike inspect).
    assert "  Supersedes:" in out
    assert "  - ADR-011" in out


# --- JSON output (REQ-006) ---------------------------------------------------


def test_json_field_order_and_values(capsys):
    rc = main(["relationships", fixture_path("relationships"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == [
        "directory",
        "recursive",
        "total_files",
        "artifacts_with_relationships",
        "relationship_count",
        "counts",
        "artifacts",
    ]
    assert payload["recursive"] is True
    assert payload["total_files"] == 5
    assert payload["artifacts_with_relationships"] == 5
    assert payload["relationship_count"] == 22
    assert payload["counts"] == EXPECTED_COUNTS
    assert payload["relationship_count"] == sum(payload["counts"].values())
    assert len(payload["artifacts"]) == 5


def test_json_per_artifact_entries(capsys):
    rc = main(["relationships", fixture_path("relationships"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    for entry in payload["artifacts"]:
        assert set(entry) == {"path", "type", "relationships"}
    decision = next(e for e in payload["artifacts"] if e["type"] == "decision")
    assert decision["relationships"]["supersedes"] == ["ADR-011"]
    requirement = next(e for e in payload["artifacts"] if e["type"] == "requirement")
    assert requirement["relationships"]["related_decisions"] == ["ADR-004", "ADR-012"]


# --- traversal flags (REQ-002, review item 5) -------------------------------


def test_top_level_sets_recursive_false(capsys):
    rc = main(["relationships", fixture_path("relationships"), "--top-level", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["recursive"] is False
    assert payload["total_files"] == 5  # the fixtures dir is flat


def test_both_flags_top_level_wins(capsys):
    rc = main(
        ["relationships", fixture_path("relationships"), "--top-level", "--recursive", "--json"]
    )
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["recursive"] is False


# --- single file (REQ-009) ---------------------------------------------------


def test_cli_single_file(capsys):
    path = fixture_path("relationships", "decision_with_links.md")
    rc = main(["relationships", path, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_files"] == 1
    assert payload["recursive"] is False
    assert payload["directory"] == path
    assert len(payload["artifacts"]) == 1
    assert "supersedes" in payload["artifacts"][0]["relationships"]


# --- empty repository (REQ-008) ---------------------------------------------


def test_empty_repo_human(capsys):
    rc = main(["relationships", fixture_path("no_relationships")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Files Inspected: 2" in out
    assert "Artifacts With Relationships: 0" in out
    assert "Relationships Found: 0" in out
    assert "By Type:" not in out


def test_empty_repo_json(capsys):
    rc = main(["relationships", fixture_path("no_relationships"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["total_files"] == 2
    assert payload["artifacts_with_relationships"] == 0
    assert payload["relationship_count"] == 0
    assert payload["counts"] == {}
    assert payload["artifacts"] == []


# --- unknown artifacts (REQ-007) --------------------------------------------


def test_unknown_artifact_counted_but_not_extracted(tmp_path):
    # An Unknown document (no schema) that nonetheless has a relationship heading.
    f = tmp_path / "notes.md"
    f.write_text("# Notes\n\n## Random Musings\n\nstuff\n\n## Related Decisions\n\n- ADR-004\n")
    report = build_relationship_report(str(tmp_path))
    assert report.total_files == 1  # counted
    assert report.artifacts_with_relationships == 0  # spec-driven: nothing extracted
    assert report.relationship_count == 0
    assert report.artifacts == []


def test_unknown_repo_exits_zero(tmp_path, capsys):
    (tmp_path / "notes.md").write_text("# Notes\n\nfree text with no sections\n")
    rc = main(["relationships", str(tmp_path)])
    assert rc == 0
    assert "Artifacts With Relationships: 0" in capsys.readouterr().out


# --- exit codes (REQ-010) ----------------------------------------------------


def test_missing_path_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["relationships", "does-not-exist-xyz"])
    assert exc.value.code == 2


def test_non_markdown_file_exits_two(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("not markdown")
    with pytest.raises(SystemExit) as exc:
        main(["relationships", str(f)])
    assert exc.value.code == 2


# --- read-only invariant (review item 6) ------------------------------------


def test_command_is_read_only(tmp_path):
    src = tmp_path / "requirement.md"
    content = (
        "# R\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] User can search.\n\n"
        "## Related Decisions\n\n- ADR-004\n"
    )
    src.write_text(content)
    before_mtime = src.stat().st_mtime_ns
    main(["relationships", str(tmp_path), "--json"])
    assert src.read_text() == content
    assert src.stat().st_mtime_ns == before_mtime
