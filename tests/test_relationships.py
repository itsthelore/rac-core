"""Tests for v0.7.0 relationship metadata.

Relationship sections (``## Related Decisions``, ``## Supersedes``, ...) are
explicit cross-artifact references (ADR-016). v0.7.0 extracts and counts them as
metadata only — no resolution, validation, or graphing. They ride the existing
``optional`` mechanism, so they are never scored, templated, or required, and
artifacts without them stay valid (REQ-012).

Fixtures live under ``fixtures/relationships/`` so they do not disturb the
directory-count assertions in ``test_inspect.py`` / ``test_stats.py``.
"""

from __future__ import annotations

import json

import pytest

from rac.cli import main
from rac.services.inspect import inspect_file, inspect_text
from rac.core.markdown import parse
from rac.services.relationships import parse_references
from rac.core.schema import schema_reference
from rac.services.stats import collect_stats
from rac.core.validation import has_errors, validate

from conftest import fixture_path

# Each fixture and the relationship keys (snake_case) it should expose via inspect.
# Note: keys are spec-driven — only relationship sections declared optional for
# that artifact type are extracted (REQ-002).
LINKED_FIXTURES = {
    "requirement": (
        "requirement_with_links.md",
        ["related_decisions", "related_roadmaps", "related_prompts", "related_designs"],
    ),
    "decision": (
        "decision_with_links.md",
        ["related_requirements", "related_roadmaps", "related_designs"],
    ),
    "roadmap": (
        "roadmap_with_links.md",
        ["related_decisions", "related_requirements", "related_prompts", "related_designs"],
    ),
    "prompt": (
        "prompt_with_links.md",
        ["related_requirements", "related_decisions", "related_roadmaps", "related_designs"],
    ),
    "design": (
        "design_with_links.md",
        ["related_requirements", "related_decisions", "related_roadmaps", "related_prompts"],
    ),
}


# --- parse_references service (amendment 4) ----------------------------------


def test_parse_references_strips_well_formed_markers():
    body = "- ADR-004\n* ADR-012\n+ ADR-020\n1. ADR-030"
    assert parse_references(body) == ["ADR-004", "ADR-012", "ADR-020", "ADR-030"]


def test_parse_references_preserves_non_marker_text():
    # A hyphen mid-token and a leading dash without a following space are NOT
    # list markers, so the text is preserved verbatim.
    body = "REQ-001 (blocked)\n../decisions/adr-004.md\n-no-space"
    assert parse_references(body) == [
        "REQ-001 (blocked)",
        "../decisions/adr-004.md",
        "-no-space",
    ]


def test_parse_references_drops_blank_lines():
    assert parse_references("\n- ADR-004\n\n- ADR-012\n") == ["ADR-004", "ADR-012"]


# --- inspect: extraction across all five artifact types (amendment 7) --------


@pytest.mark.parametrize("artifact,info", LINKED_FIXTURES.items())
def test_inspect_extracts_relationships_per_type(artifact, info):
    filename, expected_keys = info
    result = inspect_file(fixture_path("relationships", filename))
    assert result.type == artifact
    assert list(result.relationships) == expected_keys
    for key in expected_keys:
        assert result.relationships[key], f"{key} should have at least one reference"


def test_inspect_extracts_multiple_references():
    result = inspect_file(fixture_path("relationships", "requirement_with_links.md"))
    assert result.relationships["related_decisions"] == ["ADR-004", "ADR-012"]


def test_inspect_json_includes_relationships(capsys):
    rc = main(["inspect", fixture_path("relationships", "requirement_with_links.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["relationships"]["related_decisions"] == ["ADR-004", "ADR-012"]
    assert payload["relationships"]["related_designs"] == ["DESIGN-CHECKOUT-FLOW"]


def test_inspect_human_shows_relationships(capsys):
    rc = main(["inspect", fixture_path("relationships", "requirement_with_links.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Relationships:" in out
    assert "Related Decisions:" in out
    assert "- ADR-004" in out


# --- supersedes: backwards-compatible scalar exception (amendment 6) ---------


def test_supersedes_stays_top_level_not_in_relationships():
    result = inspect_file(fixture_path("relationships", "decision_with_links.md"))
    assert result.supersedes == "ADR-011"  # top-level scalar, unchanged contract
    assert "supersedes" not in result.relationships


def test_inspect_json_supersedes_scalar_not_in_relationships(capsys):
    rc = main(["inspect", fixture_path("relationships", "decision_with_links.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["supersedes"] == "ADR-011"
    assert "supersedes" not in payload["relationships"]


# --- additive / spec-driven / present_sections behavior ----------------------


def test_relationships_absent_when_no_sections():
    result = inspect_file(fixture_path("valid", "feature.md"))
    assert result.relationships == {}


def test_inspect_json_omits_relationships_when_absent(capsys):
    rc = main(["inspect", fixture_path("valid", "feature.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "relationships" not in payload


def test_empty_relationship_section_is_omitted():
    # Heading present but no references → no key (the >=1 reference rule).
    text = (
        "# Checkout\n\n## Problem\n\np\n\n## Requirements\n\n"
        "- [REQ-001] User can finish checkout.\n\n## Related Decisions\n"
    )
    result = inspect_text(text)
    assert result.type == "requirement"
    assert "related_decisions" not in result.relationships


def test_undeclared_relationship_section_is_ignored():
    # Requirement does not declare "Related Requirements" as optional, so it is
    # not extracted even though it is a relationship-vocabulary section (REQ-002).
    text = (
        "# Checkout\n\n## Problem\n\np\n\n## Requirements\n\n"
        "- [REQ-001] User can finish checkout.\n\n## Related Requirements\n\n- REQ-002\n"
    )
    result = inspect_text(text)
    assert result.type == "requirement"
    assert "related_requirements" not in result.relationships


def test_present_sections_unchanged_by_relationships():
    # Relationship sections are optional: they must not appear in present_sections.
    result = inspect_file(fixture_path("relationships", "requirement_with_links.md"))
    assert "related_decisions" not in [s.replace(" ", "_") for s in result.present_sections]
    assert set(result.present_sections) <= {"problem", "requirements"}


# --- schema & template across all five types (amendment 7) -------------------


@pytest.mark.parametrize("artifact", list(LINKED_FIXTURES))
def test_schema_json_lists_relationship_optionals(artifact, capsys):
    rc = main(["schema", artifact, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    # Every related_* optional section carries a description (amendment 5).
    related = [s for s in payload["optional"] if s.startswith("related_")]
    assert related, f"{artifact} should declare related_* optional sections"
    for section in related:
        assert payload["descriptions"][section]


@pytest.mark.parametrize("artifact", list(LINKED_FIXTURES))
def test_template_omits_relationship_sections(artifact, capsys):
    rc = main(["schema", artifact, "--template"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "## Related" not in out
    assert "## Supersedes" not in out


# --- stats: declared relationship-presence counts (amendment 9) --------------


def test_stats_counts_relationship_presence():
    s = collect_stats(fixture_path("relationships"))
    assert s.relationship_counts == {
        "related requirements": 4,
        "related decisions": 4,
        "related roadmaps": 4,
        "related prompts": 3,
        "related designs": 4,
        "supersedes": 1,
    }


def test_stats_human_shows_relationships(capsys):
    rc = main(["stats", fixture_path("relationships")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Relationships" in out
    assert "Artifacts with Related Decisions: 4" in out
    assert "Artifacts with Supersedes: 1" in out


def test_stats_json_includes_relationships_block(capsys):
    rc = main(["stats", fixture_path("relationships"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["relationships"] == {
        "related_requirements": 4,
        "related_decisions": 4,
        "related_roadmaps": 4,
        "related_prompts": 3,
        "related_designs": 4,
        "supersedes": 1,
    }


def test_stats_omits_relationships_when_none(capsys):
    rc = main(["stats", fixture_path("portfolio"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "relationships" not in payload


# --- backwards compatibility (REQ-012) ---------------------------------------


def test_artifact_without_relationships_still_valid():
    assert not has_errors(validate(parse(open(fixture_path("valid", "feature.md")).read())))


@pytest.mark.parametrize("artifact,info", LINKED_FIXTURES.items())
def test_linked_fixtures_validate(artifact, info):
    filename, _ = info
    issues = validate(parse(open(fixture_path("relationships", filename)).read()))
    assert not has_errors(issues), f"{filename} should validate without errors"
