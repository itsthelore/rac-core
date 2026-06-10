"""Tests for v0.4.2 decision metadata: status, category, supersedes.

Covers inspection (extraction + output), artifact-aware validation, and
portfolio statistics. Decision fixtures live under ``fixtures/decision/`` so they
do not disturb the directory-count assertions in ``test_inspect.py`` /
``test_stats.py``.
"""

from __future__ import annotations

import json

from conftest import fixture_path

from rac.cli import main
from rac.core.markdown import parse_file
from rac.core.validation import has_errors, validate
from rac.services.inspect import inspect_file
from rac.services.stats import collect_stats


def codes(issues):
    return {i.code for i in issues}


# --- inspection: metadata extraction ----------------------------------------


def test_inspect_extracts_decision_metadata():
    result = inspect_file(fixture_path("decision", "with_metadata.md"))
    assert result.type == "decision"
    assert result.status == "Accepted"
    assert result.category == "Architecture"
    assert result.supersedes == "ADR-003"  # leading whitespace normalized away


def test_minimal_decision_has_no_metadata():
    result = inspect_file(fixture_path("decision", "minimal.md"))
    assert result.type == "decision"
    assert result.status is None
    assert result.category is None
    assert result.supersedes is None


def test_inspect_json_includes_metadata_only_when_present(capsys):
    rc = main(["inspect", fixture_path("decision", "with_metadata.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "Accepted"
    assert payload["category"] == "Architecture"
    assert payload["supersedes"] == "ADR-003"


def test_inspect_json_omits_absent_metadata(capsys):
    rc = main(["inspect", fixture_path("decision", "minimal.md"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "status" not in payload
    assert "category" not in payload
    assert "supersedes" not in payload


def test_inspect_human_shows_metadata(capsys):
    rc = main(["inspect", fixture_path("decision", "with_metadata.md")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Status: Accepted" in out
    assert "Category: Architecture" in out
    assert "Supersedes: ADR-003" in out


# --- validation: artifact-aware dispatch ------------------------------------


def validate_decision(*parts):
    return validate(parse_file(fixture_path(*parts)))


def test_decision_is_not_validated_as_a_requirement():
    # The headline gap this release closes: a valid ADR must not fail with the
    # Requirement-only errors.
    issues = validate_decision("decision", "with_metadata.md")
    assert not has_errors(issues)
    assert "missing-problem" not in codes(issues)
    assert "missing-requirements" not in codes(issues)


def test_decision_without_metadata_is_valid():
    issues = validate_decision("decision", "minimal.md")
    assert not has_errors(issues)
    # Optional metadata absent -> no warnings or errors about it (REQ-007).
    assert codes(issues) == set()


def test_invalid_status_is_an_error():
    issues = validate_decision("decision", "bad_status.md")
    assert "invalid-decision-status" in codes(issues)
    assert has_errors(issues)


def test_invalid_category_is_an_error():
    issues = validate_decision("decision", "bad_category.md")
    assert "invalid-decision-category" in codes(issues)
    assert has_errors(issues)


def test_all_supported_status_values_pass():
    for status in ("Proposed", "Accepted", "Superseded", "Deprecated"):
        text = (
            f"# ADR\n\n## Status\n\n{status}\n\n## Context\n\nc\n\n"
            "## Decision\n\nd\n\n## Consequences\n\nx\n"
        )
        from rac.core.markdown import parse

        assert "invalid-decision-status" not in codes(validate(parse(text)))


def test_all_supported_category_values_pass():
    from rac.core.markdown import parse

    for category in ("Architecture", "Product", "Process", "Technical", "Other"):
        text = (
            f"# ADR\n\n## Category\n\n{category}\n\n## Context\n\nc\n\n"
            "## Decision\n\nd\n\n## Consequences\n\nx\n"
        )
        assert "invalid-decision-category" not in codes(validate(parse(text)))


def test_status_value_match_is_case_insensitive():
    from rac.core.markdown import parse

    text = (
        "# ADR\n\n## Status\n\naccepted\n\n## Context\n\nc\n\n"
        "## Decision\n\nd\n\n## Consequences\n\nx\n"
    )
    assert "invalid-decision-status" not in codes(validate(parse(text)))


def test_missing_required_decision_section_is_an_error():
    from rac.core.markdown import parse

    # A decision missing ## Consequences (still classifies as a decision).
    text = "# ADR\n\n## Status\n\nAccepted\n\n## Context\n\nc\n\n## Decision\n\nd\n"
    issues = validate(parse(text))
    assert "missing-consequences" in codes(issues)


# --- statistics: separated aggregation --------------------------------------


def test_stats_counts_decisions_separately():
    s = collect_stats(fixture_path("decision", "portfolio"))
    assert s.decision_count == 3
    # Decisions never count as requirement features.
    assert s.files_found == 0
    assert s.total_requirements == 0


def test_stats_status_and_category_breakdown():
    s = collect_stats(fixture_path("decision", "portfolio"))
    assert s.decision_status_counts == {"Accepted": 1, "Proposed": 1}
    assert s.decision_category_counts == {"Architecture": 1, "Process": 1}


def test_stats_human_shows_decisions_section(capsys):
    rc = main(["stats", fixture_path("decision", "portfolio")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Decisions" in out
    assert "Total: 3" in out
    assert "Accepted: 1" in out
    assert "Architecture: 1" in out


def test_stats_json_includes_decisions_block(capsys):
    rc = main(["stats", fixture_path("decision", "portfolio"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["decisions"]["count"] == 3
    assert payload["decisions"]["by_status"] == {"Accepted": 1, "Proposed": 1}
    assert payload["decisions"]["by_category"] == {"Architecture": 1, "Process": 1}


def test_stats_json_omits_decisions_block_for_requirement_only(capsys):
    rc = main(["stats", fixture_path("portfolio"), "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "decisions" not in payload
