"""Tests for artifact improvement (`rac improve`, v0.5.0).

Advisory, deterministic, schema-driven, read-only. Requirement artifacts get
missing-section suggestions; other known types and Unknown get explanatory
guidance. Exit code is always 0 for a completed analysis, 2 for usage errors.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from rac.cli import main
from rac.improve import improve_file, improve_text

from conftest import fixture_path

# A requirement missing a *required* section (Requirements) but still classifying
# as a requirement — it keeps enough recommended sections to clear the threshold.
NO_REQUIREMENTS = (
    "# Feature\n\n## Problem\n\np\n\n## Success Metrics\n\n- m\n\n## Risks\n\n- r\n"
)


# --- service layer ----------------------------------------------------------


def test_requirement_reports_missing_recommended():
    result = improve_file(fixture_path("inspect", "requirement.md"))
    assert result.type == "requirement"
    assert result.missing_required == []
    assert "risks" in result.missing_recommended
    assert "assumptions" in result.missing_recommended


def test_requirement_reports_missing_required():
    result = improve_text(NO_REQUIREMENTS)
    assert result.type == "requirement"
    assert result.missing_required == ["requirements"]
    assert result.missing_recommended == ["assumptions"]


def test_complete_requirement_has_nothing_missing():
    complete = (
        "# Feature\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n\n"
        "## Success Metrics\n\n- m\n\n## Risks\n\n- r\n\n## Assumptions\n\n- a\n"
    )
    result = improve_text(complete)
    assert result.type == "requirement"
    assert result.missing_required == []
    assert result.missing_recommended == []


def test_unknown_artifact_yields_no_suggestions():
    result = improve_file(fixture_path("inspect", "ambiguous.md"))
    assert result.type == "unknown"
    assert result.missing_required == []
    assert result.missing_recommended == []


def test_decision_is_out_of_scope_for_v050():
    result = improve_file(fixture_path("decision", "with_metadata.md"))
    assert result.type == "decision"
    assert not result.supported
    assert result.missing_required == []


def test_improve_does_not_depend_on_typescore():
    # Decoupling guard: improvement must not reach into classification scoring.
    import inspect as _inspect

    import rac.improve as improve_mod

    src = _inspect.getsource(improve_mod)
    assert "TypeScore" not in src
    assert "score_artifacts" not in src


# --- JSON contract (ADR-007) ------------------------------------------------


def test_json_shape_is_stable(capsys):
    rc = main(["improve", fixture_path("inspect", "requirement.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"type", "missing_required", "missing_recommended"}
    assert payload["type"] == "requirement"
    # closest_type is reserved on the model but not serialized in v0.5.0.
    assert "closest_type" not in payload


def test_json_uses_snake_cased_section_names(capsys):
    # "success metrics" -> "success_metrics" when missing.
    text = "# F\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
    monkey_stdin(text)
    rc = main(["improve", "-", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "success_metrics" in payload["missing_recommended"]


def test_json_unknown_has_empty_arrays(capsys):
    rc = main(["improve", fixture_path("inspect", "ambiguous.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "unknown"
    assert payload["missing_required"] == []
    assert payload["missing_recommended"] == []


# --- template (REQ-003) -----------------------------------------------------


def test_template_emits_todo_and_guidance(capsys):
    rc = main(["improve", fixture_path("inspect", "requirement.md"), "--template"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "## Risks" in out
    assert "_TODO_" in out
    assert "<!--" in out  # schema guidance comment


def test_template_orders_required_before_recommended(capsys):
    monkey_stdin(NO_REQUIREMENTS)
    rc = main(["improve", "-", "--template"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.index("## Requirements") < out.index("## Assumptions")


# --- human output -----------------------------------------------------------


def test_human_output_lists_missing(capsys):
    rc = main(["improve", fixture_path("inspect", "requirement.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Requirement" in out
    assert "Missing Recommended:" in out
    assert "Risks" in out


def test_human_unknown_message(capsys):
    rc = main(["improve", fixture_path("inspect", "ambiguous.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Unable to generate improvement guidance." in out
    assert "could not be determined" in out


def test_human_decision_is_generic_not_requirement_worded(capsys):
    rc = main(["improve", fixture_path("decision", "with_metadata.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Decision" in out
    assert "not currently available for this artifact type" in out
    assert "Requirement" not in out  # no hard-coded requirement wording


# --- pipelines (ADR-011) ----------------------------------------------------


def monkey_stdin(text: str) -> None:
    import sys

    sys.stdin = io.StringIO(text)


def test_stdin_matches_file(monkeypatch, capsys):
    text = Path(fixture_path("inspect", "requirement.md")).read_text()
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    rc = main(["improve", "-", "--json"])
    assert rc == 0
    from_stdin = json.loads(capsys.readouterr().out)
    assert from_stdin == improve_text(text).to_dict()


# --- usage errors (exit 2) --------------------------------------------------


def test_missing_file_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["improve", fixture_path("inspect", "does_not_exist.md")])
    assert exc.value.code == 2


def test_non_markdown_file_exits_two(tmp_path):
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(SystemExit) as exc:
        main(["improve", str(bad)])
    assert exc.value.code == 2


def test_json_and_template_are_mutually_exclusive():
    with pytest.raises(SystemExit):  # argparse mutually-exclusive error
        main(["improve", fixture_path("inspect", "requirement.md"), "--json", "--template"])


# --- read-only (REQ-004) ----------------------------------------------------


def test_improve_does_not_modify_the_file(tmp_path):
    f = tmp_path / "req.md"
    original = "# F\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] x\n"
    f.write_text(original)
    before = f.stat().st_mtime_ns
    main(["improve", str(f), "--template"])
    assert f.read_text() == original
    assert f.stat().st_mtime_ns == before
