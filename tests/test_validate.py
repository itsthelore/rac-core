"""Tests for the validation rules."""

from __future__ import annotations

from rac.core.markdown import parse, parse_file
from rac.core.validation import has_errors, validate

from conftest import fixture_path


def codes(issues):
    return {i.code for i in issues}


def validate_fixture(*parts):
    return validate(parse_file(fixture_path(*parts)))


def test_valid_file_has_no_errors():
    issues = validate_fixture("valid", "feature.md")
    assert not has_errors(issues)
    assert codes(issues) == set()  # fully clean: no warnings either


def test_minimal_file_is_valid_but_warns_on_optional_sections():
    issues = validate_fixture("valid", "minimal.md")
    assert not has_errors(issues)
    assert "missing-success-metrics" in codes(issues)
    assert "missing-risks" in codes(issues)


def test_missing_title():
    assert "missing-title" in codes(validate_fixture("invalid", "missing_title.md"))


def test_multiple_titles():
    issues = validate_fixture("invalid", "multiple_titles.md")
    assert "multiple-titles" in codes(issues)
    assert has_errors(issues)
    # One error regardless of count, pointing at the first extra title.
    extra = [i for i in issues if i.code == "multiple-titles"]
    assert len(extra) == 1
    assert extra[0].line == 11


def test_multiple_titles_reports_single_error_for_many():
    text = "# One\n\n## Problem\n\nx\n\n## Requirements\n\n[REQ-001] do it\n\n# Two\n\n# Three\n"
    issues = validate(parse(text))
    assert sum(1 for i in issues if i.code == "multiple-titles") == 1


def test_missing_problem():
    assert "missing-problem" in codes(validate_fixture("invalid", "missing_problem.md"))


def test_missing_requirements():
    assert "missing-requirements" in codes(
        validate_fixture("invalid", "missing_requirements.md")
    )


def test_malformed_id():
    issues = validate_fixture("invalid", "malformed_id.md")
    assert "malformed-req-id" in codes(issues)
    assert has_errors(issues)


def test_missing_id():
    assert "req-missing-id" in codes(validate_fixture("invalid", "missing_id.md"))


def test_empty_req_text():
    assert "empty-req-text" in codes(validate_fixture("invalid", "empty_req_text.md"))


def test_duplicate_id():
    issues = validate_fixture("invalid", "duplicate_ids.md")
    assert "duplicate-req-id" in codes(issues)
    # Reported once even though the ID appears twice.
    assert sum(1 for i in issues if i.code == "duplicate-req-id") == 1


def test_warnings_fixture_flags_ambiguous_verb_and_duplicate_text():
    issues = validate_fixture("valid", "warnings.md")
    assert not has_errors(issues)
    assert "ambiguous-verb" in codes(issues)
    assert "duplicate-req-text" in codes(issues)


def test_empty_problem_warning():
    issues = validate(parse("# T\n\n## Problem\n\n## Requirements\n\n[REQ-001] x\n"))
    assert "empty-problem" in codes(issues)


def test_too_many_requirements_warning():
    reqs = "\n".join(f"[REQ-{i:03d}] requirement number {i}" for i in range(1, 60))
    text = f"# T\n\n## Problem\n\nx\n\n## Requirements\n\n{reqs}\n"
    issues = validate(parse(text))
    assert "too-many-requirements" in codes(issues)
