"""Tests for the Design artifact type (v0.6.3).

Design is a first-class artifact for UX, interaction, and interface knowledge.
It rides the shared, schema-driven machinery (classify, validate, stats,
improve, schema) like Roadmap and Prompt. RAC does not render UI, manage design
systems, or add design-specific improvement engines.
"""

from __future__ import annotations

import io
import json

from conftest import fixture_path

import rac.services.improve as improve_mod
from rac.cli import main
from rac.core.artifacts import ARTIFACT_SPECS, spec_for
from rac.core.classification import classify
from rac.core.markdown import parse, parse_file
from rac.core.schema import available_schemas, schema_reference
from rac.core.validation import has_errors, validate
from rac.services.improve import improve_file, improve_text, supports_improve
from rac.services.inspect import inspect_file
from rac.services.stats import collect_stats


def _stdin(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


def _codes(parts):
    return {i.code for i in validate(parse_file(fixture_path(*parts)))}


# --- classification ---------------------------------------------------------


def test_design_classifies_as_design():
    result = inspect_file(fixture_path("design", "valid.md"))
    assert result.type == "design"
    assert result.confidence >= 0.5


def test_minimal_design_classifies_on_required_sections():
    # Four required sections only -> 4/6.5, above the 0.5 threshold.
    assert inspect_file(fixture_path("design", "minimal.md")).type == "design"


def test_incomplete_but_sufficient_design_classifies_as_design():
    result = inspect_file(fixture_path("design", "missing_constraints.md"))
    assert result.type == "design"
    assert "constraints" in result.missing_sections


def test_too_incomplete_design_like_doc_is_unknown():
    text = "# TUI Navigation Design\n\n## Context\n\nx\n\n## Design\n\ny\n"
    assert classify(parse(text)).type == "unknown"


def test_requirement_does_not_classify_as_design():
    assert inspect_file(fixture_path("valid", "feature.md")).type == "requirement"


def test_design_does_not_classify_as_requirement():
    assert inspect_file(fixture_path("design", "valid.md")).type != "requirement"


def test_ui_design_themed_titles_do_not_drive_classification():
    title_only = "# TUI Visual Design\n\nNotes about layout and navigation.\n"
    assert classify(parse(title_only)).type == "unknown"

    requirement_about_ui = (
        "# UI Design Requirements\n\n"
        "## Problem\n\n"
        "Teams need consistent dashboard layout guidance.\n\n"
        "## Requirements\n\n"
        "[REQ-001] The system shall show dashboard navigation consistently.\n"
    )
    assert classify(parse(requirement_about_ui)).type == "requirement"


def test_design_carries_no_metadata():
    spec = spec_for("design")
    assert spec is not None
    assert spec.metadata == {}


# --- validation -------------------------------------------------------------


def test_valid_design_has_no_errors():
    assert not has_errors(validate(parse_file(fixture_path("design", "valid.md"))))


def test_minimal_design_has_no_errors():
    # Missing recommended/optional sections must never fail validation.
    assert not has_errors(validate(parse_file(fixture_path("design", "minimal.md"))))


def test_design_missing_required_section_fails():
    assert "missing-constraints" in _codes(("design", "missing_constraints.md"))


def test_design_missing_required_error_codes_are_hyphenated():
    missing_user_need = (
        "# D\n\n## Context\n\nc\n\n## Design\n\nd\n\n## Constraints\n\nx\n\n## Rationale\n\nr\n"
    )
    product = parse(missing_user_need)
    assert classify(product).type == "design"
    assert "missing-user-need" in {i.code for i in validate(product)}


def test_design_missing_title_fails():
    text = "## Context\n\nc\n\n## User Need\n\nu\n\n## Design\n\nd\n\n## Constraints\n\nx\n"
    assert "missing-title" in {i.code for i in validate(parse(text))}


# --- schema reference & template --------------------------------------------


def test_design_is_a_registered_schema():
    assert "design" in available_schemas()


def test_schema_reference_shape():
    ref = schema_reference("design")
    assert ref is not None
    assert ref.required == ["context", "user need", "design", "constraints"]
    assert ref.recommended == [
        "rationale",
        "alternatives",
        "accessibility",
        "style guidance",
        "open questions",
    ]
    assert ref.optional == [
        "related requirements",
        "related decisions",
        "related roadmaps",
        "related prompts",
    ]


def test_schema_json_includes_optional_relationship_sections(capsys):
    rc = main(["schema", "design", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "design"
    assert payload["required"] == ["context", "user_need", "design", "constraints"]
    assert payload["recommended"] == [
        "rationale",
        "alternatives",
        "accessibility",
        "style_guidance",
        "open_questions",
    ]
    assert payload["optional"] == [
        "related_requirements",
        "related_decisions",
        "related_roadmaps",
        "related_prompts",
    ]


def test_schema_human_shows_design_sections(capsys):
    rc = main(["schema", "design"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Design" in out
    assert "User Need" in out
    assert "Style Guidance" in out
    assert "Related Prompts" in out


def test_template_omits_optional_relationship_sections(capsys):
    rc = main(["schema", "design", "--template"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "## Context" in out
    assert "## User Need" in out
    assert "## Open Questions" in out
    assert "## Related Requirements" not in out
    assert "## Related Decisions" not in out
    assert "## Related Roadmaps" not in out
    assert "## Related Prompts" not in out


def test_template_passes_validation(monkeypatch):
    ref = schema_reference("design")
    assert ref is not None
    from rac.output import render_schema_template

    template = render_schema_template(ref)
    _stdin(monkeypatch, template)
    assert main(["validate", "-"]) == 0


# --- improvement (structural only, schema-driven) ---------------------------


def test_design_is_supported_when_guidance_is_complete():
    spec = spec_for("design")
    assert spec is not None
    assert supports_improve(spec) is True


def test_complete_design_has_nothing_to_improve():
    result = improve_file(fixture_path("design", "valid.md"))
    assert result.type == "design"
    assert result.missing_required == []
    assert result.missing_recommended == []


def test_minimal_design_reports_missing_recommended():
    result = improve_file(fixture_path("design", "minimal.md"))
    assert result.type == "design"
    assert result.missing_required == []
    assert result.missing_recommended == [
        "rationale",
        "alternatives",
        "accessibility",
        "style guidance",
        "open questions",
    ]
    assert result.guidance["accessibility"]


def test_incomplete_design_reports_missing_required_and_recommended():
    result = improve_text(
        "# D\n\n## Context\n\nc\n\n## User Need\n\nu\n\n## Design\n\nd\n\n## Rationale\n\nr\n"
    )
    assert result.type == "design"
    assert result.missing_required == ["constraints"]
    assert "accessibility" in result.missing_recommended


def test_improve_json_shape_is_structural_only(capsys):
    rc = main(["improve", fixture_path("design", "minimal.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {
        "type",
        "missing_required",
        "missing_recommended",
        "guidance",
    }
    assert payload["type"] == "design"
    assert "style_guidance" in payload["missing_recommended"]
    assert payload["guidance"]["open_questions"] == [
        "What still needs to be decided?",
        "What should be validated or explored further?",
    ]


def test_improve_human_lists_missing_with_guidance(capsys):
    rc = main(["improve", fixture_path("design", "minimal.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Design" in out
    assert "Missing Recommended:" in out
    assert "Style Guidance" in out


def test_improve_does_not_modify_the_design(tmp_path):
    f = tmp_path / "design.md"
    content = (
        "# D\n\n## Context\n\nc\n\n## User Need\n\nu\n\n## Design\n\nd\n\n## Constraints\n\nx\n"
    )
    f.write_text(content)
    before = f.stat().st_mtime_ns
    main(["improve", str(f), "--template"])
    assert f.read_text() == content
    assert f.stat().st_mtime_ns == before


def test_improve_support_is_artifact_spec_driven():
    for spec in ARTIFACT_SPECS:
        complete = set(spec.expected) <= set(spec.guidance)
        assert supports_improve(spec) is complete

    public = {name for name in vars(improve_mod) if not name.startswith("_")}
    assert not any("design" in name for name in public)


def test_design_guidance_has_no_work_management_fields():
    forbidden_fields = [
        "owner:",
        "assignee:",
        "status:",
        "sprint:",
        "due date:",
        "deadline:",
        "priority:",
    ]
    spec = spec_for("design")
    assert spec is not None
    blob = " ".join(line for lines in spec.guidance.values() for line in lines).casefold()
    for field in forbidden_fields:
        assert field not in blob


# --- inspection CLI ---------------------------------------------------------


def test_cli_inspect_human(capsys):
    rc = main(["inspect", fixture_path("design", "valid.md")])
    assert rc == 0
    assert "Artifact Type: Design" in capsys.readouterr().out


def test_cli_inspect_json(capsys):
    rc = main(["inspect", fixture_path("design", "valid.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "design"
    assert "status" not in payload
    assert "category" not in payload


def test_cli_validate_invalid_design_exits_one():
    assert main(["validate", fixture_path("design", "missing_constraints.md")]) == 1


def test_cli_validate_valid_design_exits_zero():
    assert main(["validate", fixture_path("design", "valid.md")]) == 0


# --- statistics: separated aggregation --------------------------------------


def test_stats_counts_designs_separately():
    s = collect_stats(fixture_path("design"))
    assert s.design_count == 3
    assert s.files_found == 0
    assert s.total_requirements == 0
    assert s.valid_designs == 2
    assert len(s.invalid_designs) == 1
    assert s.invalid_designs[0].path.endswith("missing_constraints.md")
    assert s.invalid_designs[0].error_codes == ["missing-constraints"]


def test_stats_human_shows_designs_section(capsys):
    rc = main(["stats", fixture_path("design")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Designs" in out
    assert "Total: 3" in out
    assert "Valid: 2" in out
    assert "Invalid Designs (1)" in out


def test_stats_json_includes_designs_block(capsys):
    rc = main(["stats", fixture_path("design"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["designs"]["count"] == 3
    assert payload["designs"]["valid"] == 2
    assert payload["designs"]["invalid"] == [
        {
            "file": fixture_path("design", "missing_constraints.md"),
            "errors": ["missing-constraints"],
        }
    ]


def test_requirement_only_stats_omit_designs_block(capsys):
    rc = main(["stats", fixture_path("portfolio"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "designs" not in payload


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


def test_prompt_validation_unchanged():
    product = parse_file(fixture_path("prompt", "valid.md"))
    assert classify(product).type == "prompt"
    assert not has_errors(validate(product))
