"""Tests for v0.7.2 relationship validation (`rac relationships --validate`).

Validation resolves explicit references against artifact identifiers discovered in
the repository and reports missing targets, ambiguous targets, duplicate
identifiers, and self-references — deterministically, read-only, with
validation-style exit codes (0 ok / 1 issues / 2 usage). See ADR-016.

Fixtures live under `fixtures/relationship_validation/<scenario>/`.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from rac.core.artifacts import spec_for
from rac.cli import main
from rac.core.classification import classify
from rac.core.markdown import parse, parse_file
from rac.services.relationships import (
    ISSUE_DUPLICATE_IDENTIFIER,
    ISSUE_SELF_REFERENCE,
    ISSUE_TARGET_AMBIGUOUS,
    ISSUE_TARGET_NOT_FOUND,
    artifact_identifier,
    validate_relationships,
    validate_relationships_file,
)

from conftest import fixture_path


def _scenario(name: str) -> str:
    return fixture_path("relationship_validation", name)


# --- identifier resolution precedence (REQ-002) -----------------------------


def test_identifier_explicit_id_section_wins():
    # Step 1: an explicit ## ID section overrides everything, casing preserved.
    product = parse("# Title\n\n## ID\n\nADR-XYZ\n\n## Context\n\nc\n")
    assert artifact_identifier(product, spec_for("decision"), "/x/adr-004-foo.md") == "ADR-XYZ"


def test_identifier_spec_id_field():
    # Step 2: the type's declared id_field section (no real spec sets it today).
    product = parse("# Title\n\n## Key\n\nDEC-7\n")
    spec = replace(spec_for("decision"), id_field="key")
    assert artifact_identifier(product, spec, "/x/whatever.md") == "DEC-7"


def test_identifier_recognized_prefix_from_stem():
    # Step 3: leading <letters>-<digits> prefix of the filename stem.
    product = parse("# Parser Strategy\n\n## Context\n\nc\n")
    assert artifact_identifier(product, spec_for("decision"), "/x/adr-004-parser-strategy.md") == "adr-004"


def test_identifier_falls_back_to_full_stem():
    # Step 4: no recognized prefix -> the whole stem.
    product = parse("# Q3 Roadmap\n\n## Outcomes\n\no\n\n## Initiatives\n\ni\n")
    assert artifact_identifier(product, spec_for("roadmap"), "/x/roadmap-q3.md") == "roadmap-q3"


def test_identifier_matching_is_case_insensitive():
    # ADR-004 reference resolves to adr-004.md (resolved fixture has both).
    report = validate_relationships(_scenario("resolved"))
    assert report.ok  # references use ADR-004 / REQ-001 against adr-004.md / req-001.md


# --- resolved repository (REQ-003 / REQ-005) --------------------------------


def test_resolved_repo_passes():
    report = validate_relationships(_scenario("resolved"))
    assert report.relationships_checked == 4
    assert report.validation_issues == 0
    assert report.ok


def test_resolved_cli_exits_zero(capsys):
    rc = main(["relationships", _scenario("resolved"), "--validate"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Relationship Validation" in out
    assert "Relationships Checked: 4" in out
    assert "Validation Issues: 0" in out


# --- broken references (REQ-004) --------------------------------------------


def test_broken_reference_detected():
    report = validate_relationships(_scenario("broken"))
    assert not report.ok
    assert report.validation_issues == 1
    issue = report.issues[0]
    assert issue.code == ISSUE_TARGET_NOT_FOUND
    assert issue.target == "ADR-999"
    assert issue.relationship == "related_decisions"
    assert issue.source_path.endswith("search.md")


def test_broken_cli_exits_one(capsys):
    rc = main(["relationships", _scenario("broken"), "--validate"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "Broken Relationships" in out
    assert "✗ ADR-999 not found" in out


def test_broken_json(capsys):
    rc = main(["relationships", _scenario("broken"), "--validate", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    assert list(payload) == [
        "directory",
        "recursive",
        "relationships_checked",
        "validation_issues",
        "issues",
    ]
    assert payload["relationships_checked"] == 1
    assert payload["validation_issues"] == 1
    issue = payload["issues"][0]
    assert set(issue) == {"source_path", "relationship", "target", "code"}
    assert issue["code"] == ISSUE_TARGET_NOT_FOUND
    assert issue["target"] == "ADR-999"


# --- duplicate identifiers (REQ-009) ----------------------------------------


def test_duplicate_identifier_detected():
    report = validate_relationships(_scenario("duplicate"))
    assert not report.ok
    assert report.validation_issues == 1
    issue = report.issues[0]
    assert issue.code == ISSUE_DUPLICATE_IDENTIFIER
    # Identifier derives from the filename stem (the title is never used), so the
    # discovered casing here is the lowercase stem.
    assert issue.identifier == "adr-004"
    assert len(issue.paths) == 2
    assert issue.paths == sorted(issue.paths)  # deterministic ordering


def test_duplicate_json_shape(capsys):
    rc = main(["relationships", _scenario("duplicate"), "--validate", "--json"])
    assert rc == 1
    payload = json.loads(capsys.readouterr().out)
    issue = payload["issues"][0]
    assert set(issue) == {"identifier", "paths", "code"}
    assert issue["code"] == ISSUE_DUPLICATE_IDENTIFIER


# --- ambiguous target: duplicate + per-reference ambiguity (item 4 / item 8) --


def test_ambiguous_target_emits_both_issues():
    report = validate_relationships(_scenario("ambiguous_target"))
    assert not report.ok
    codes = [i.code for i in report.issues]
    # Duplicate (repo-level) is emitted first, then the per-reference ambiguity.
    assert codes == [ISSUE_DUPLICATE_IDENTIFIER, ISSUE_TARGET_AMBIGUOUS]
    ambiguous = report.issues[1]
    assert ambiguous.target == "ADR-004"
    assert ambiguous.source_path.endswith("req-001.md")


def test_ambiguous_cli_exits_one(capsys):
    rc = main(["relationships", _scenario("ambiguous_target"), "--validate"])
    assert rc == 1
    assert "✗ ADR-004 ambiguous" in capsys.readouterr().out


# --- self reference (REQ-010) -----------------------------------------------


def test_self_reference_detected():
    report = validate_relationships(_scenario("self_reference"))
    assert not report.ok
    assert report.validation_issues == 1
    issue = report.issues[0]
    assert issue.code == ISSUE_SELF_REFERENCE
    assert issue.target == "ADR-004"
    assert issue.relationship == "supersedes"


def test_self_reference_cli_exits_one(capsys):
    rc = main(["relationships", _scenario("self_reference"), "--validate"])
    assert rc == 1
    assert "✗ ADR-004 self-reference" in capsys.readouterr().out


# --- unknown artifacts (REQ-008) --------------------------------------------


def test_unknown_artifact_is_a_valid_target_but_emits_no_references(tmp_path):
    # An Unknown file whose stem yields an id (legacy-api) satisfies an incoming
    # reference, yet contributes no outgoing relationships of its own.
    (tmp_path / "legacy-api.md").write_text("# Legacy API\n\nFree text, no sections.\n")
    (tmp_path / "req-001.md").write_text(
        "# Search\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] User can search.\n\n"
        "## Related Designs\n\n- legacy-api\n"
    )
    # Sanity: legacy-api.md is Unknown.
    assert classify(parse_file(str(tmp_path / "legacy-api.md"))).type == "unknown"
    report = validate_relationships(str(tmp_path))
    assert report.relationships_checked == 1  # only req-001 declares a reference
    assert report.ok  # the reference resolves to the Unknown file


# --- single-file validation (REQ-009 / item 6) ------------------------------


def test_single_file_index_is_just_that_file():
    # req-001.md references ADR-004, which is not in a single-file index -> broken.
    report = validate_relationships_file(_scenario("resolved") + "/req-001.md")
    assert report.recursive is False
    assert report.relationships_checked == 1
    assert report.issues[0].code == ISSUE_TARGET_NOT_FOUND


# --- exit codes (REQ-007) ---------------------------------------------------


def test_missing_path_exits_two():
    with pytest.raises(SystemExit) as exc:
        main(["relationships", "does-not-exist-xyz", "--validate"])
    assert exc.value.code == 2


def test_non_markdown_file_exits_two(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("not markdown")
    with pytest.raises(SystemExit) as exc:
        main(["relationships", str(f), "--validate"])
    assert exc.value.code == 2


# --- read-only + non-validate unchanged -------------------------------------


def test_validate_is_read_only(tmp_path):
    src = tmp_path / "req-001.md"
    content = (
        "# Search\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] User can search.\n\n"
        "## Related Decisions\n\n- ADR-004\n"
    )
    src.write_text(content)
    before = src.stat().st_mtime_ns
    main(["relationships", str(tmp_path), "--validate", "--json"])
    assert src.read_text() == content
    assert src.stat().st_mtime_ns == before


def test_non_validate_inspection_still_works(capsys):
    # Without --validate the command is the v0.7.1 inspection (exit 0 regardless).
    rc = main(["relationships", _scenario("broken")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Files Inspected:" in out
    assert "Validation Issues" not in out
