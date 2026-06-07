"""Tests for the Prompt artifact type (v0.6.2).

Prompt is a first-class artifact recognized by its Objective/Input/Instructions/
Output sections. It rides the shared, schema-driven machinery (classify, validate,
stats, improve, schema) the same way Requirement, Decision, and Roadmap do — no
prompt-specific engine. Per ADR-002/REQ-012 RAC never calls AI; per ADR-017/REQ-011
prompts are knowledge, never executed.
"""

from __future__ import annotations

import io
import json

import pytest

import rac.services.improve as improve_mod
from rac.core.artifacts import ARTIFACT_SPECS, spec_for
from rac.cli import main
from rac.core.classification import classify
from rac.services.improve import improve_file, improve_text, supports_improve
from rac.services.inspect import inspect_file
from rac.core.markdown import parse, parse_file
from rac.core.schema import available_schemas, schema_reference
from rac.services.stats import collect_stats
from rac.core.validation import has_errors, validate

from conftest import fixture_path


def _stdin(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def _codes(parts):
    return {i.code for i in validate(parse_file(fixture_path(*parts)))}


# --- classification ---------------------------------------------------------


def test_prompt_classifies_as_prompt():
    result = inspect_file(fixture_path("prompt", "valid.md"))
    assert result.type == "prompt"
    assert result.confidence >= 0.5


def test_minimal_prompt_classifies_on_required_sections():
    # Four required sections only -> 4/5.5, above the 0.5 threshold.
    assert inspect_file(fixture_path("prompt", "minimal.md")).type == "prompt"


def test_three_of_four_required_still_classifies_as_prompt():
    # REQ-005 (corrected): Objective + Input + Instructions = 3/4 -> 0.55 -> Prompt.
    result = inspect_file(fixture_path("prompt", "missing_output.md"))
    assert result.type == "prompt"


def test_two_of_four_required_is_unknown():
    # Agreed REQ-005 resolution: too little Prompt signal stays Unknown, rather
    # than changing the global classification threshold.
    text = "# P\n\n## Objective\n\nx\n\n## Instructions\n\ny\n"
    assert classify(parse(text)).type == "unknown"


def test_requirement_does_not_classify_as_prompt():
    assert inspect_file(fixture_path("valid", "feature.md")).type == "requirement"


def test_ai_themed_requirement_stays_requirement():
    # A Requirement *about* prompts/AI (Problem + Requirements structure) must not
    # be misclassified as a Prompt — classification is heading-based, not topical.
    text = (
        "# AI Prompt Library Feature\n\n"
        "## Problem\n\n"
        "Teams keep prompts and AI instructions scattered across chats; we need a "
        "prompt library inside the product.\n\n"
        "## Requirements\n\n"
        "[REQ-001] User can save a prompt with an objective and instructions.\n"
        "[REQ-002] User can search prompts by expected output.\n"
    )
    assert classify(parse(text)).type == "requirement"


def test_prompt_carries_no_metadata():
    spec = spec_for("prompt")
    assert spec is not None
    assert spec.metadata == {}


# --- synonyms (artifact-scoped) ---------------------------------------------


def test_expected_output_synonym_classifies_as_prompt():
    # "## Expected Output" maps to the canonical "output" section for scoring.
    text = (
        "# P\n\n## Objective\n\no\n\n## Input\n\ni\n\n## Instructions\n\nx\n\n"
        "## Expected Output\n\nz\n"
    )
    assert classify(parse(text)).type == "prompt"


def test_input_and_output_specification_synonyms_classify_as_prompt():
    text = (
        "# P\n\n## Objective\n\no\n\n## Input Specification\n\ni\n\n"
        "## Instructions\n\nx\n\n## Output Specification\n\nz\n"
    )
    assert classify(parse(text)).type == "prompt"


# --- validation -------------------------------------------------------------


def test_valid_prompt_has_no_errors():
    assert not has_errors(validate(parse_file(fixture_path("prompt", "valid.md"))))


def test_minimal_prompt_has_no_errors():
    # Missing recommended/optional sections must never fail validation (REQ-006).
    assert not has_errors(validate(parse_file(fixture_path("prompt", "minimal.md"))))


def test_prompt_missing_required_section_fails():
    assert "missing-output" in _codes(("prompt", "missing_output.md"))


def test_prompt_missing_required_error_codes():
    # Stable per-section error codes (REQ-006). Use 3-of-4 docs so each still
    # classifies as Prompt while missing a different required section.
    missing_input = "# P\n\n## Objective\n\no\n\n## Instructions\n\nx\n\n## Output\n\ny\n"
    assert classify(parse(missing_input)).type == "prompt"
    assert "missing-input" in {i.code for i in validate(parse(missing_input))}

    missing_objective = "# P\n\n## Input\n\ni\n\n## Instructions\n\nx\n\n## Output\n\ny\n"
    assert classify(parse(missing_objective)).type == "prompt"
    assert "missing-objective" in {i.code for i in validate(parse(missing_objective))}


def test_prompt_validation_uses_canonical_headings():
    # Synonyms aid classification but validation expects canonical headings, like
    # Decision/Roadmap. "Expected Output" classifies as Prompt yet still wants Output.
    text = (
        "# P\n\n## Objective\n\no\n\n## Input\n\ni\n\n## Instructions\n\nx\n\n"
        "## Expected Output\n\nz\n"
    )
    product = parse(text)
    assert classify(product).type == "prompt"
    assert "missing-output" in {i.code for i in validate(product)}


# --- schema reference & template --------------------------------------------


def test_prompt_is_a_registered_schema():
    assert "prompt" in available_schemas()


def test_schema_reference_shape():
    ref = schema_reference("prompt")
    assert ref is not None
    assert ref.required == ["objective", "input", "instructions", "output"]
    assert ref.recommended == ["constraints", "examples", "evaluation"]
    assert ref.optional == [
        "related requirements",
        "related decisions",
        "related roadmaps",
        "related designs",
    ]


def test_schema_json_includes_optional_relationship_sections(capsys):
    rc = main(["schema", "prompt", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "prompt"
    assert payload["required"] == ["objective", "input", "instructions", "output"]
    assert payload["optional"] == [
        "related_requirements",
        "related_decisions",
        "related_roadmaps",
        "related_designs",
    ]


def test_schema_human_shows_optional_relationship_sections(capsys):
    rc = main(["schema", "prompt"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Prompt" in out
    assert "Related Requirements" in out


def test_template_omits_optional_relationship_sections(capsys):
    rc = main(["schema", "prompt", "--template"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "## Objective" in out
    assert "## Output" in out
    assert "## Constraints" in out
    assert "## Related Requirements" not in out
    assert "## Related Decisions" not in out
    assert "## Related Roadmaps" not in out


def test_template_passes_validation(monkeypatch):
    ref = schema_reference("prompt")
    assert ref is not None
    from rac.output import render_schema_template

    template = render_schema_template(ref)
    _stdin(monkeypatch, template)
    assert main(["validate", "-"]) == 0


# --- improvement (structural only, schema-driven) ---------------------------


def test_prompt_is_supported_when_guidance_is_complete():
    spec = spec_for("prompt")
    assert spec is not None
    assert supports_improve(spec) is True


def test_complete_prompt_has_nothing_to_improve():
    result = improve_file(fixture_path("prompt", "valid.md"))
    assert result.type == "prompt"
    assert result.missing_required == []
    assert result.missing_recommended == []


def test_minimal_prompt_reports_missing_recommended():
    result = improve_file(fixture_path("prompt", "minimal.md"))
    assert result.type == "prompt"
    assert result.missing_required == []
    assert result.missing_recommended == ["constraints", "examples", "evaluation"]
    assert result.guidance["constraints"]


def test_improve_json_shape_is_structural_only(capsys):
    rc = main(["improve", fixture_path("prompt", "minimal.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "type",
        "missing_required",
        "missing_recommended",
        "guidance",
    }
    assert payload["type"] == "prompt"
    assert "constraints" in payload["missing_recommended"]


def test_improve_human_lists_missing_with_guidance(capsys):
    rc = main(["improve", fixture_path("prompt", "minimal.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Prompt" in out
    assert "Missing Recommended:" in out
    assert "Evaluation" in out


def test_improve_does_not_modify_the_prompt(tmp_path):
    f = tmp_path / "prompt.md"
    content = (
        "# P\n\n## Objective\n\no\n\n## Input\n\ni\n\n## Instructions\n\nx\n\n"
        "## Output\n\ny\n"
    )
    f.write_text(content)
    before = f.stat().st_mtime_ns
    main(["improve", str(f), "--template"])
    assert f.read_text() == content
    assert f.stat().st_mtime_ns == before


def test_prompt_guidance_has_no_work_management_fields():
    # ADR-017 / REQ-011: knowledge, not work. Field-oriented guard (normal language
    # like "process" or "format" stays allowed).
    forbidden_fields = [
        "owner:",
        "assignee:",
        "status:",
        "sprint:",
        "due date:",
        "deadline:",
        "priority:",
    ]
    spec = spec_for("prompt")
    assert spec is not None
    blob = " ".join(
        line for lines in spec.guidance.values() for line in lines
    ).casefold()
    for field in forbidden_fields:
        assert field not in blob


def test_improve_support_is_artifact_spec_driven():
    # Prompt improve works via complete ArtifactSpec guidance through the shared
    # pipeline — there is no prompt-specific improve engine.
    public = {name for name in vars(improve_mod) if not name.startswith("_")}
    assert not any("prompt" in name for name in public)


# --- inspection CLI ---------------------------------------------------------


def test_cli_inspect_human(capsys):
    rc = main(["inspect", fixture_path("prompt", "valid.md")])
    assert rc == 0
    assert "Artifact Type: Prompt" in capsys.readouterr().out


def test_cli_inspect_json(capsys):
    rc = main(["inspect", fixture_path("prompt", "valid.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "prompt"
    assert "status" not in payload
    assert "category" not in payload


def test_cli_validate_invalid_prompt_exits_one():
    assert main(["validate", fixture_path("prompt", "missing_output.md")]) == 1


def test_cli_validate_valid_prompt_exits_zero():
    assert main(["validate", fixture_path("prompt", "valid.md")]) == 0


# --- statistics: separated aggregation --------------------------------------


def test_stats_counts_prompts_separately():
    s = collect_stats(fixture_path("prompt"))
    assert s.prompt_count == 3
    assert s.files_found == 0  # prompts are never requirement features
    assert s.total_requirements == 0
    assert s.valid_prompts == 2  # valid.md + minimal.md
    assert len(s.invalid_prompts) == 1
    assert s.invalid_prompts[0].path.endswith("missing_output.md")


def test_stats_human_shows_prompts_section(capsys):
    rc = main(["stats", fixture_path("prompt")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Prompts" in out
    assert "Total: 3" in out
    assert "Valid: 2" in out
    assert "Invalid Prompts (1)" in out


def test_stats_json_includes_prompts_block(capsys):
    rc = main(["stats", fixture_path("prompt"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["prompts"]["count"] == 3
    assert payload["prompts"]["valid"] == 2
    assert payload["prompts"]["invalid"][0]["file"].endswith("missing_output.md")


# --- regression: existing artifact behavior is unchanged --------------------


def test_requirement_validation_unchanged():
    assert not has_errors(validate(parse_file(fixture_path("valid", "feature.md"))))
    assert "missing-title" in _codes(("invalid", "missing_title.md"))


def test_decision_validation_unchanged():
    product = parse_file(fixture_path("decision", "with_metadata.md"))
    assert classify(product).type == "decision"
    assert not has_errors(validate(product))


def test_roadmap_validation_unchanged():
    product = parse_file(fixture_path("roadmap", "valid.md"))
    assert classify(product).type == "roadmap"
    assert not has_errors(validate(product))


def test_requirement_only_stats_omit_prompts_block(capsys):
    rc = main(["stats", fixture_path("portfolio"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "prompts" not in payload


def test_roadmap_stats_omit_prompts_block(capsys):
    rc = main(["stats", fixture_path("roadmap"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "roadmaps" in payload
    assert "prompts" not in payload
