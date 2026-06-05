"""Tests for artifact inspection (`rac inspect`)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from rac.artifacts import ARTIFACT_SPECS
from rac.classification import CONFIDENCE_THRESHOLD, score_artifacts
from rac.cli import main
from rac.inspect import (
    inspect_directory,
    inspect_file,
    inspect_text,
)
from rac.parser import parse

from conftest import fixture_path

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- service layer ----------------------------------------------------------


def test_artifact_specs_are_the_two_concrete_types():
    names = {spec.name for spec in ARTIFACT_SPECS}
    assert names == {"requirement", "decision"}


def test_parse_captures_title_and_sections():
    product = parse("# Title\n\n## Problem\n\nx\n\n## Requirements\n\ny\n")
    assert product.title == "Title"
    assert list(product.sections) == ["problem", "requirements"]


def test_classify_requirement():
    result = inspect_file(fixture_path("inspect", "requirement.md"))
    assert result.type == "requirement"
    assert result.confidence >= CONFIDENCE_THRESHOLD
    assert "problem" in result.present_sections
    assert "requirements" in result.present_sections
    assert "assumptions" in result.missing_sections  # recommended, absent


def test_classify_decision():
    result = inspect_file(fixture_path("inspect", "decision.md"))
    assert result.type == "decision"
    assert "context" in result.present_sections
    assert "decision" in result.present_sections


def test_alias_matching():
    # "## Alternatives" should count as the "alternatives considered" section.
    text = (
        "# ADR-2 Thing\n\n## Context\n\nc\n\n## Decision\n\nd\n\n"
        "## Consequences\n\nx\n\n## Alternatives\n\ny\n"
    )
    result = inspect_text(text)
    assert result.type == "decision"
    assert "alternatives considered" in result.present_sections


def test_unknown_for_ambiguous():
    result = inspect_file(fixture_path("inspect", "ambiguous.md"))
    assert result.type == "unknown"
    assert result.missing_sections == []


def test_unknown_for_empty():
    result = inspect_text("")
    assert result.type == "unknown"
    assert result.confidence == 0.0


def test_dogfood_repo_artifacts():
    # RAC against RAC: an ADR is a Decision; a roadmap spec is a Requirement.
    adr = REPO_ROOT / "planning/adr/adr-010-documents-are-not-artifacts.md"
    roadmap = REPO_ROOT / "planning/roadmap/v0.4-inspect.md"
    assert inspect_file(str(adr)).type == "decision"
    assert inspect_file(str(roadmap)).type == "requirement"


# --- synonyms ---------------------------------------------------------------


def test_synonym_counts_as_canonical_section():
    # "## Success Criteria" should satisfy the requirement's success-metrics slot.
    text = (
        "# Feature\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n\n"
        "## Success Criteria\n\n- hits target\n"
    )
    result = inspect_text(text)
    assert result.type == "requirement"
    assert "success metrics" in result.present_sections
    assert "success metrics" not in result.missing_sections


def test_synonym_is_case_insensitive():
    text = "# F\n\n## Problem\n\np\n\n## Requirements\n\nr\n\n## KPIs\n\n- x\n"
    assert "success metrics" in inspect_text(text).present_sections


# --- scoring breakdown / verbose --------------------------------------------


def test_score_artifacts_breakdown():
    product = parse(Path(fixture_path("inspect", "decision.md")).read_text())
    top = score_artifacts(product)[0]
    assert top.name == "decision"
    assert set(top.matched_required) == {"context", "decision", "consequences"}
    assert "status" in top.matched_recommended
    # required (3) + 0.5×(status) = 3.5 / (3 + 0.5×3 recommended) = 3.5 / 4.5
    assert top.points == 3.5 and top.ceiling == 4.5


def test_cli_inspect_verbose(capsys):
    rc = main(["inspect", fixture_path("inspect", "requirement.md"), "--verbose"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Required Matches:" in out
    assert "Recommended Matches:" in out
    assert "Score:" in out and "/ 3.5" in out


# --- directory inspection ---------------------------------------------------


def test_inspect_directory_recursive_vs_top_level():
    d = fixture_path("inspect")
    top = inspect_directory(d, recursive=False)
    rec = inspect_directory(d, recursive=True)
    assert top.total_files == 3  # requirement, decision, ambiguous
    assert rec.total_files == 4  # + nested/another_requirement.md
    assert rec.counts["requirement"] == 2
    assert rec.counts["decision"] == 1
    assert rec.counts["unknown"] == 1


def test_cli_dir_inspect_human(capsys):
    rc = main(["inspect", fixture_path("inspect")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Files Inspected: 4" in out
    assert "Requirements: 2" in out
    assert "Decisions: 1" in out
    assert "Unknown: 1" in out


def test_cli_dir_inspect_json_is_versioned_and_flat(capsys):
    rc = main(["inspect", fixture_path("inspect"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["recursive"] is True
    assert payload["summary"]["total_files"] == 4
    assert payload["summary"]["counts"]["requirement"] == 2
    # File entries are flat: path/type/confidence only (no present/missing).
    entry = payload["files"][0]
    assert set(entry) == {"path", "type", "confidence"}


def test_cli_dir_inspect_top_level_flag(capsys):
    rc = main(["inspect", fixture_path("inspect"), "--top-level"])
    assert rc == 0
    assert "Files Inspected: 3" in capsys.readouterr().out


def test_cli_dir_inspect_recursive_flag_accepted(capsys):
    # --recursive is the default; accepted as a no-op for clarity.
    rc = main(["inspect", fixture_path("inspect"), "--recursive"])
    assert rc == 0
    assert "Files Inspected: 4" in capsys.readouterr().out


def test_dogfood_directory_targets():
    # RAC-formatted roadmap specs classify as Requirements; newer exploratory
    # roadmap formats may remain Unknown until their schemas are formalized.
    roadmap = inspect_directory(str(REPO_ROOT / "planning/roadmap"))
    paths_by_type = {f.path: f.type for f in roadmap.files}
    assert paths_by_type[
        str(REPO_ROOT / "planning/roadmap/v0.5.2-schema.md")
    ] == "requirement"
    assert paths_by_type[
        str(REPO_ROOT / "planning/roadmap/v0.6-roadmaps.md")
    ] == "requirement"
    # The well-formed ADRs classify as Decision.
    adr = REPO_ROOT / "planning/adr/adr-010-documents-are-not-artifacts.md"
    assert inspect_file(str(adr)).type == "decision"


# --- CLI --------------------------------------------------------------------


def test_cli_inspect_human(capsys):
    rc = main(["inspect", fixture_path("inspect", "requirement.md")])
    assert rc == 0
    assert "Artifact Type: Requirement" in capsys.readouterr().out


def test_cli_inspect_json_shape(capsys):
    rc = main(["inspect", fixture_path("inspect", "requirement.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "type",
        "confidence",
        "present_sections",
        "missing_sections",
    }
    assert payload["type"] == "requirement"


def test_cli_inspect_stdin(monkeypatch, capsys):
    text = Path(fixture_path("inspect", "decision.md")).read_text()
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    rc = main(["inspect", "-"])
    assert rc == 0
    assert "Artifact Type: Decision" in capsys.readouterr().out


def test_cli_inspect_unknown_exits_zero(capsys):
    rc = main(["inspect", fixture_path("inspect", "ambiguous.md")])
    assert rc == 0  # Unknown is a successful outcome
    assert "Artifact Type: Unknown" in capsys.readouterr().out


def test_cli_inspect_unsupported_type_exits_two(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(SystemExit) as exc:
        main(["inspect", str(bad)])
    assert exc.value.code == 2


def test_cli_inspect_missing_file_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["inspect", fixture_path("inspect", "does_not_exist.md")])
    assert exc.value.code == 2


# --- ingest --stdout --------------------------------------------------------


def test_cli_ingest_stdout_flag(capsys):
    rc = main(["ingest", fixture_path("ingest", "sample.md"), "--stdout"])
    assert rc == 0
    assert "# Already Markdown" in capsys.readouterr().out


def test_cli_ingest_stdout_conflicts_with_output(tmp_path):
    out = tmp_path / "out.md"
    with pytest.raises(SystemExit):  # argparse mutually-exclusive error
        main(["ingest", fixture_path("ingest", "sample.md"), "-o", str(out), "--stdout"])
