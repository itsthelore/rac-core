"""Tests for the Roadmap artifact type (v0.6.0).

Roadmap is a first-class artifact recognized by its Outcomes/Initiatives sections.
It rides the shared, schema-driven machinery (classify, validate, stats, improve,
schema) the same way Requirement and Decision do. Per ADR-017 and the v0.6.0 spec
it carries no work-management metadata (owners, dates, status), and improvement
stays strictly structural (missing sections + schema guidance, never quality).
"""

from __future__ import annotations

import io
import json

import pytest

import rac.improve as improve_mod
from rac.artifacts import ARTIFACT_SPECS, spec_for
from rac.cli import main
from rac.classification import classify
from rac.improve import improve_file, improve_text, supports_improve
from rac.inspect import inspect_file
from rac.parser import parse, parse_file
from rac.schema import available_schemas, schema_reference
from rac.stats import collect_stats
from rac.validate import has_errors, validate

from conftest import fixture_path


def _stdin(monkeypatch, text: str) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


# --- classification ---------------------------------------------------------


def test_roadmap_classifies_as_roadmap():
    result = inspect_file(fixture_path("roadmap", "valid.md"))
    assert result.type == "roadmap"
    assert result.confidence >= 0.5


def test_minimal_roadmap_classifies_on_required_sections_alone():
    # Outcomes + Initiatives only -> 2/3.5 fit, above the 0.5 threshold.
    result = inspect_file(fixture_path("roadmap", "minimal.md"))
    assert result.type == "roadmap"


def test_requirement_does_not_classify_as_roadmap():
    # A Requirement has no Outcomes/Initiatives, so it never wins the roadmap slot.
    assert inspect_file(fixture_path("valid", "feature.md")).type == "requirement"


def test_roadmap_carries_no_metadata():
    # Roadmap manages knowledge, not work: no status/category/supersedes fields.
    spec = spec_for("roadmap")
    assert spec is not None
    assert spec.metadata == {}


# --- validation -------------------------------------------------------------


def _codes(parts):
    return {i.code for i in validate(parse_file(fixture_path(*parts)))}


def test_valid_roadmap_has_no_errors():
    assert not has_errors(validate(parse_file(fixture_path("roadmap", "valid.md"))))


def test_minimal_roadmap_has_no_errors():
    # Missing recommended sections must never fail validation (REQ-003).
    assert not has_errors(validate(parse_file(fixture_path("roadmap", "minimal.md"))))


def test_roadmap_missing_required_section_fails():
    codes = _codes(("roadmap", "missing_initiatives.md"))
    assert "missing-initiatives" in codes


def test_roadmap_missing_title_fails(monkeypatch):
    text = "## Outcomes\n\n- o\n\n## Initiatives\n\n- i\n"
    issues = validate(parse(text))
    assert "missing-title" in {i.code for i in issues}


# --- schema reference & template --------------------------------------------


def test_roadmap_is_a_registered_schema():
    assert "roadmap" in available_schemas()


def test_schema_reference_shape():
    ref = schema_reference("roadmap")
    assert ref is not None
    assert ref.required == ["outcomes", "initiatives"]
    assert ref.recommended == ["success measures", "assumptions", "risks"]
    assert ref.optional == [
        "related decisions",
        "related requirements",
        "related prompts",
        "related designs",
    ]


def test_schema_json_includes_optional_relationship_sections(capsys):
    rc = main(["schema", "roadmap", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "roadmap"
    assert payload["required"] == ["outcomes", "initiatives"]
    assert payload["optional"] == [
        "related_decisions",
        "related_requirements",
        "related_prompts",
        "related_designs",
    ]


def test_schema_human_shows_optional_relationship_sections(capsys):
    rc = main(["schema", "roadmap"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Roadmap" in out
    assert "Related Decisions" in out


def test_template_omits_optional_relationship_sections(capsys):
    rc = main(["schema", "roadmap", "--template"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "## Outcomes" in out
    assert "## Initiatives" in out
    assert "## Success Measures" in out
    # Optional relationship sections stay out of the starter (v0.7.x territory).
    assert "## Related Decisions" not in out
    assert "## Related Requirements" not in out


def test_template_passes_validation(monkeypatch):
    ref = schema_reference("roadmap")
    assert ref is not None
    from rac.outputs import render_schema_template

    template = render_schema_template(ref)
    _stdin(monkeypatch, template)
    assert main(["validate", "-"]) == 0


# --- improvement (structural only) ------------------------------------------


def test_roadmap_is_supported_when_guidance_is_complete():
    spec = spec_for("roadmap")
    assert spec is not None
    assert supports_improve(spec) is True


def test_complete_roadmap_has_nothing_to_improve():
    result = improve_file(fixture_path("roadmap", "valid.md"))
    assert result.type == "roadmap"
    assert result.missing_required == []
    assert result.missing_recommended == []


def test_minimal_roadmap_reports_missing_recommended():
    result = improve_file(fixture_path("roadmap", "minimal.md"))
    assert result.type == "roadmap"
    assert result.missing_required == []
    assert result.missing_recommended == ["success measures", "assumptions", "risks"]
    assert result.guidance["success measures"]


def test_improve_json_shape_is_structural_only(capsys):
    rc = main(["improve", fixture_path("roadmap", "minimal.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # Exactly the shared structural contract — no quality/score fields.
    assert set(payload) == {
        "type",
        "missing_required",
        "missing_recommended",
        "guidance",
    }
    assert payload["type"] == "roadmap"
    assert "success_measures" in payload["missing_recommended"]
    assert payload["guidance"]["success_measures"] == [
        "How will the team know the roadmap is succeeding?",
        "What observable signals would show progress?",
    ]
    # risks stays single-line (REQ-006).
    assert payload["guidance"]["risks"] == [
        "What could prevent these outcomes from being achieved?"
    ]


def test_improve_human_lists_missing_with_guidance(capsys):
    rc = main(["improve", fixture_path("roadmap", "minimal.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Roadmap" in out
    assert "Missing Recommended:" in out
    assert "Success Measures" in out


def test_success_measures_guidance_is_enriched():
    # v0.6.1 hardening: Success Measures carries both prompting questions
    # (REQ-004/006). Enrichment flows from the ArtifactSpec, not a renderer.
    spec = spec_for("roadmap")
    assert spec is not None
    assert spec.guidance["success measures"] == (
        "How will the team know the roadmap is succeeding?",
        "What observable signals would show progress?",
    )


def test_improve_separates_missing_required_from_recommended():
    # A roadmap with enough signal to classify (Outcomes + 3 recommended) but
    # missing the required Initiatives section reports them in separate buckets.
    text = (
        "# R\n\n## Outcomes\n\n- o\n\n## Success Measures\n\n- m\n\n"
        "## Assumptions\n\n- a\n\n## Risks\n\n- r\n"
    )
    result = improve_text(text)
    assert result.type == "roadmap"
    assert result.missing_required == ["initiatives"]
    assert result.missing_recommended == []


def test_improve_template_orders_required_before_recommended(monkeypatch, capsys):
    # Only Outcomes present -> Initiatives (required) must precede the recommended
    # sections in the emitted template (REQ-005).
    text = (
        "# R\n\n## Outcomes\n\n- o\n\n## Assumptions\n\n- a\n\n## Risks\n\n- r\n"
    )
    _stdin(monkeypatch, text)
    rc = main(["improve", "-", "--template"])
    assert rc == 0
    out = capsys.readouterr().out
    assert out.index("## Initiatives") < out.index("## Success Measures")


def test_improve_does_not_modify_the_roadmap(tmp_path):
    f = tmp_path / "roadmap.md"
    content = "# R\n\n## Outcomes\n\n- o\n\n## Initiatives\n\n- i\n"
    f.write_text(content)
    before = f.stat().st_mtime_ns
    main(["improve", str(f), "--template"])
    assert f.read_text() == content
    assert f.stat().st_mtime_ns == before


# --- inspection CLI ---------------------------------------------------------


def test_cli_inspect_human(capsys):
    rc = main(["inspect", fixture_path("roadmap", "valid.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Artifact Type: Roadmap" in out


def test_cli_inspect_json(capsys):
    rc = main(["inspect", fixture_path("roadmap", "valid.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["type"] == "roadmap"
    # No decision-style metadata leaks onto a roadmap.
    assert "status" not in payload
    assert "category" not in payload


def test_cli_validate_invalid_roadmap_exits_one(capsys):
    rc = main(["validate", fixture_path("roadmap", "missing_initiatives.md")])
    assert rc == 1


def test_cli_validate_valid_roadmap_exits_zero():
    assert main(["validate", fixture_path("roadmap", "valid.md")]) == 0


# --- statistics: separated aggregation --------------------------------------


def test_stats_counts_roadmaps_separately():
    s = collect_stats(fixture_path("roadmap"))
    assert s.roadmap_count == 3
    # Roadmaps never count as requirement features.
    assert s.files_found == 0
    assert s.total_requirements == 0
    assert s.valid_roadmaps == 2  # valid.md + minimal.md
    assert len(s.invalid_roadmaps) == 1
    assert s.invalid_roadmaps[0].path.endswith("missing_initiatives.md")


def test_stats_human_shows_roadmaps_section(capsys):
    rc = main(["stats", fixture_path("roadmap")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Roadmaps" in out
    assert "Total: 3" in out
    assert "Valid: 2" in out
    assert "Invalid Roadmaps (1)" in out


def test_stats_json_includes_roadmaps_block(capsys):
    rc = main(["stats", fixture_path("roadmap"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["roadmaps"]["count"] == 3
    assert payload["roadmaps"]["valid"] == 2
    assert payload["roadmaps"]["invalid"][0]["file"].endswith("missing_initiatives.md")


# --- regression: existing artifact behavior is unchanged (Amendment 6) ------


def test_requirement_validation_unchanged():
    # The original Requirement rules still fire exactly as before.
    assert not has_errors(validate(parse_file(fixture_path("valid", "feature.md"))))
    assert "missing-title" in _codes(("invalid", "missing_title.md"))
    assert "missing-requirements" in _codes(("invalid", "missing_requirements.md"))


def test_decision_validation_unchanged():
    # A Decision still routes to the Decision validator, not roadmap/requirement.
    product = parse_file(fixture_path("decision", "with_metadata.md"))
    assert classify(product).type == "decision"
    assert not has_errors(validate(product))


def test_requirement_only_stats_omit_roadmaps_block(capsys):
    rc = main(["stats", fixture_path("portfolio"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # Additive guarantee: no roadmaps key when the portfolio has none.
    assert "roadmaps" not in payload


def test_decision_stats_unchanged_and_omit_roadmaps(capsys):
    rc = main(["stats", fixture_path("decision", "portfolio"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decisions"]["count"] == 3
    assert "roadmaps" not in payload


# --- architecture: improvement stays ArtifactSpec-driven --------------------


def test_improve_support_is_artifact_spec_driven():
    # The real v0.6.0 achievement: improve support is earned through complete
    # ArtifactSpec guidance, via the shared pipeline — never per-type logic.
    for spec in ARTIFACT_SPECS:
        complete = set(spec.expected) <= set(spec.guidance)
        assert supports_improve(spec) is complete

    # No artifact-specific improve engine exists: the public surface is generic.
    public = {name for name in vars(improve_mod) if not name.startswith("_")}
    artifact_specific = {
        name
        for name in public
        if any(t in name for t in ("roadmap", "requirement", "decision"))
    }
    assert artifact_specific == set()


def test_roadmap_guidance_has_no_work_management_fields():
    # ADR-017 / REQ-008: guidance must not push work-management *fields* onto
    # roadmaps. Field-oriented (not a broad word ban): normal strategic language
    # like "milestone" or "timeline" stays allowed.
    forbidden_fields = [
        "owner:",
        "assignee:",
        "status:",
        "sprint:",
        "due date:",
        "deadline:",
        "priority:",
    ]
    spec = spec_for("roadmap")
    assert spec is not None
    blob = " ".join(
        line for lines in spec.guidance.values() for line in lines
    ).casefold()
    for field in forbidden_fields:
        assert field not in blob
