"""Tests for artifact inspection (`rac inspect`)."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from rac.artifacts import ARTIFACT_SPECS
from rac.cli import main
from rac.inspect import (
    CONFIDENCE_THRESHOLD,
    classify,
    extract_sections,
    inspect_file,
    inspect_text,
)

from conftest import fixture_path

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- service layer ----------------------------------------------------------


def test_artifact_specs_are_the_two_concrete_types():
    names = {spec.name for spec in ARTIFACT_SPECS}
    assert names == {"requirement", "decision"}


def test_extract_sections_returns_title_and_headings():
    doc = extract_sections("# Title\n\n## Problem\n\nx\n\n## Requirements\n\ny\n")
    assert doc.title == "Title"
    assert doc.headings == ["problem", "requirements"]


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
