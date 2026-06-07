"""Tests for artifact improvement (`rac improve`).

Advisory, deterministic, schema-driven, read-only. Supported artifact types get
missing-section suggestions and guidance. Exit code is always 0 for a completed
analysis, 2 for usage errors.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from rac.core.artifacts import ARTIFACT_SPECS, spec_for
from rac.core.classification import classify
from rac.cli import main
from rac.services.improve import improve_file, improve_text, supports_improve
from rac.core.markdown import parse, parse_file
from rac.services.stats import collect_stats
from rac.core.validation import validate

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


def test_decision_is_supported_when_guidance_is_complete():
    result = improve_file(fixture_path("decision", "with_metadata.md"))
    assert result.type == "decision"
    assert result.supported
    assert result.missing_required == []
    assert result.missing_recommended == ["alternatives considered"]
    assert "alternatives considered" in result.guidance


def test_improve_does_not_depend_on_typescore():
    # Decoupling guard: improvement must not reach into classification scoring.
    import inspect as _inspect

    import rac.services.improve as improve_mod

    src = _inspect.getsource(improve_mod)
    assert "TypeScore" not in src
    assert "score_artifacts" not in src


# --- JSON contract (ADR-007) ------------------------------------------------


def test_json_shape_is_stable(capsys):
    rc = main(["improve", fixture_path("inspect", "requirement.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "type",
        "missing_required",
        "missing_recommended",
        "guidance",
    }
    assert payload["type"] == "requirement"
    assert set(payload["guidance"]) == set(payload["missing_recommended"])
    assert payload["guidance"]["risks"]
    # closest_type is reserved on the model but not serialized.
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
    assert payload["guidance"] == {}


def test_json_guidance_is_map_keyed_by_snake_cased_sections(capsys):
    rc = main(["improve", fixture_path("inspect", "requirement.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload["guidance"], dict)
    assert sorted(payload["guidance"]) == ["assumptions", "risks"]
    assert payload["guidance"]["risks"] == [
        "What could prevent successful delivery?",
        "What dependencies or unknowns exist?",
    ]


def test_json_decision_guidance(capsys):
    rc = main(["improve", fixture_path("decision", "with_metadata.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "decision"
    assert payload["missing_required"] == []
    assert payload["missing_recommended"] == ["alternatives_considered"]
    assert payload["guidance"]["alternatives_considered"] == [
        "What other options were weighed?",
        "Why were they not chosen?",
    ]


# --- template (REQ-003) -----------------------------------------------------


def test_template_emits_todo_and_guidance(capsys):
    rc = main(["improve", fixture_path("inspect", "requirement.md"), "--template"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "## Risks" in out
    assert "_TODO_" in out
    assert "<!-- What could prevent successful delivery? -->" in out


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
    assert "What could prevent successful delivery?" in out


def test_human_unknown_message(capsys):
    rc = main(["improve", fixture_path("inspect", "ambiguous.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Unable to generate improvement guidance." in out
    assert "could not be determined" in out


def test_human_decision_shows_guidance(capsys):
    rc = main(["improve", fixture_path("decision", "with_metadata.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Decision" in out
    assert "Alternatives Considered" in out
    assert "What other options were weighed?" in out
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


# --- guidance model (v0.5.1) ------------------------------------------------


def test_supported_specs_have_guidance_for_every_expected_section():
    supported = {"requirement", "decision"}
    for spec in ARTIFACT_SPECS:
        if spec.name not in supported:
            continue
        assert supports_improve(spec)
        assert set(spec.expected) <= set(spec.guidance)


def test_incomplete_guidance_makes_known_type_unsupported(monkeypatch, capsys):
    spec = spec_for("requirement")
    assert spec is not None
    original = spec.guidance["risks"]
    monkeypatch.delitem(spec.guidance, "risks")
    assert not supports_improve(spec)

    rc = main(["improve", fixture_path("inspect", "requirement.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Requirement" in out
    assert "not currently available for this artifact type" in out

    spec.guidance["risks"] = original


def test_guidance_is_informational_metadata_only(monkeypatch):
    spec = spec_for("requirement")
    assert spec is not None
    original = spec.guidance["risks"]
    product = parse_file(fixture_path("inspect", "requirement.md"))
    stats_dir = fixture_path("portfolio")

    before_classify = classify(product)
    before_validate = [(i.severity, i.code, i.message) for i in validate(product)]
    before_stats = collect_stats(stats_dir)
    before_stats_tuple = (
        before_stats.files_found,
        before_stats.total_requirements,
        before_stats.total_metrics,
        before_stats.total_risks,
        before_stats.decision_status_counts,
        before_stats.decision_category_counts,
    )
    before_improve = improve_file(fixture_path("inspect", "requirement.md"))

    monkeypatch.setitem(spec.guidance, "risks", ("Changed guidance text?",))

    after_classify = classify(product)
    after_validate = [(i.severity, i.code, i.message) for i in validate(product)]
    after_stats = collect_stats(stats_dir)
    after_stats_tuple = (
        after_stats.files_found,
        after_stats.total_requirements,
        after_stats.total_metrics,
        after_stats.total_risks,
        after_stats.decision_status_counts,
        after_stats.decision_category_counts,
    )
    after_improve = improve_file(fixture_path("inspect", "requirement.md"))

    assert after_classify == before_classify
    assert after_validate == before_validate
    assert after_stats_tuple == before_stats_tuple
    assert before_improve.guidance["risks"] == list(original)
    assert after_improve.guidance["risks"] == ["Changed guidance text?"]
