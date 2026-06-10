"""Tests for the validation rules."""

from __future__ import annotations

import json

from conftest import fixture_path

from rac.cli import main
from rac.core.markdown import parse, parse_file
from rac.core.validation import has_errors, validate
from rac.services.validate import (
    STATUS_INVALID,
    STATUS_SKIPPED,
    STATUS_VALID,
    validate_directory,
)


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
    assert "missing-requirements" in codes(validate_fixture("invalid", "missing_requirements.md"))


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


# ---------------------------------------------------------------------------
# Directory validation (v0.7.9) — `rac validate <directory>`
# ---------------------------------------------------------------------------


def test_directory_counts_valid_and_invalid():
    result = validate_directory(fixture_path("portfolio"))
    assert result.checked == 4  # feature_a, feature_b, broken, sub/feature_c
    assert result.valid == 3
    assert result.invalid == 1
    assert not result.ok
    by_path = {f.path: f for f in result.files}
    broken = by_path[fixture_path("portfolio", "broken.md")]
    assert broken.status == STATUS_INVALID
    assert "missing-title" in {i.code for i in broken.issues}


def test_directory_top_level_skips_subdirectories():
    result = validate_directory(fixture_path("portfolio"), recursive=False)
    assert result.checked == 3  # sub/feature_c.md excluded


def test_directory_skips_unknown_artifacts():
    # all_types contains one file per artifact type plus one unknown document;
    # the unknown file is reported as skipped, never validated (portfolio
    # semantics — the requirement fallback is single-file only).
    result = validate_directory(fixture_path("portfolio_summary", "all_types"))
    assert result.skipped == 1
    statuses = {f.artifact_type: f.status for f in result.files}
    assert statuses["unknown"] == STATUS_SKIPPED
    assert all(
        f.status in (STATUS_VALID, STATUS_INVALID)
        for f in result.files
        if f.artifact_type != "unknown"
    )


def test_directory_results_sorted_by_path():
    result = validate_directory(fixture_path("portfolio"))
    paths = [f.path for f in result.files]
    assert paths == sorted(paths)


def test_directory_empty_is_ok(tmp_path):
    result = validate_directory(str(tmp_path))
    assert result.ok
    assert result.files == []


def test_cli_directory_exit_codes(capsys):
    assert main(["validate", fixture_path("portfolio")]) == 1
    capsys.readouterr()
    assert main(["validate", fixture_path("valid")]) == 0


def test_cli_directory_human_output(capsys):
    main(["validate", fixture_path("portfolio")])
    out = capsys.readouterr().out
    assert "FAIL" in out
    assert "broken.md" in out
    assert "missing-title" in out
    # valid files are counted, not listed
    assert "feature_a.md" not in out
    assert "3 valid, 1 invalid" in out


def test_cli_directory_json_contract(capsys):
    rc = main(["validate", fixture_path("portfolio"), "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["valid"] is False
    assert payload["summary"] == {
        "total_files": 4,
        "checked": 4,
        "valid": 3,
        "invalid": 1,
        "skipped_unknown": 0,
    }
    statuses = {f["path"]: f["status"] for f in payload["files"]}
    assert statuses[fixture_path("portfolio", "broken.md")] == "invalid"


def test_cli_single_file_behavior_unchanged(capsys):
    # Unknown single files still fall back to the legacy requirement rules.
    rc = main(["validate", fixture_path("portfolio_summary", "all_types", "unknown.md")])
    assert rc == 1
