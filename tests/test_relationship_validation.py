"""Tests for v0.7.2 relationship validation (`rac relationships --validate`).

Validation resolves explicit references against artifact identifiers discovered in
the repository and reports missing targets, ambiguous targets, duplicate
identifiers, and self-references — deterministically, read-only, with
validation-style exit codes (0 ok / 1 issues / 2 usage). See ADR-016.

Fixtures live under `fixtures/relationship_validation/<scenario>/`.
"""

from __future__ import annotations

import json

import pytest
from conftest import fixture_path

from rac.cli import main
from rac.core.classification import classify
from rac.core.markdown import parse_file
from rac.services.relationships import (
    ISSUE_DUPLICATE_IDENTIFIER,
    ISSUE_EDGE_UNSUPPORTED,
    ISSUE_SELF_REFERENCE,
    ISSUE_TARGET_AMBIGUOUS,
    ISSUE_TARGET_NOT_FOUND,
    ISSUE_TARGET_SUPERSEDED,
    validate_relationships,
    validate_relationships_file,
)


def _scenario(name: str) -> str:
    return fixture_path("relationship_validation", name)


# --- identifier resolution precedence (REQ-002) -----------------------------


def test_identifier_matching_is_case_insensitive():
    # ADR-004 reference resolves to adr-004.md (resolved fixture has both).
    report = validate_relationships(_scenario("resolved"))
    assert report.ok  # references use ADR-004 / REQ-001 against adr-004.md / req-001.md


# --- self-type relationships (v0.13.5) --------------------------------------

_ROADMAP = "# {t}\n\n## Outcomes\n\no\n\n## Initiatives\n\ni\n"
_DECISION = "# {t}\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nq\n"


def test_self_type_relationships_resolve(tmp_path):
    (tmp_path / "v1.md").write_text(_ROADMAP.format(t="One"), encoding="utf-8")
    (tmp_path / "v2.md").write_text(
        _ROADMAP.format(t="Two") + "\n## Related Roadmaps\n\n- v1\n", encoding="utf-8"
    )
    (tmp_path / "adr-001.md").write_text(_DECISION.format(t="A1"), encoding="utf-8")
    (tmp_path / "adr-002.md").write_text(
        _DECISION.format(t="A2") + "\n## Related Decisions\n\n- adr-001\n", encoding="utf-8"
    )
    report = validate_relationships(str(tmp_path))
    assert report.relationships_checked == 2  # one roadmap->roadmap, one decision->decision
    assert report.validation_issues == 0
    assert report.ok


def test_self_type_broken_reference_is_reported(tmp_path):
    (tmp_path / "v2.md").write_text(
        _ROADMAP.format(t="Two") + "\n## Related Roadmaps\n\n- v-missing\n", encoding="utf-8"
    )
    report = validate_relationships(str(tmp_path))
    assert not report.ok
    assert report.validation_issues == 1


# --- external ticket references (ADR-087) -----------------------------------


def test_external_ticket_reference_is_never_broken(tmp_path):
    # A ## Related Tickets entry resolves to no in-corpus artifact by design, so
    # it is exempt from referential integrity — never reported not-found, and not
    # counted among the resolved references (it is format-linted by `rac validate`).
    (tmp_path / "adr-001.md").write_text(
        _DECISION.format(t="A1") + "\n## Related Tickets\n\n- PROJ-1234\n- some-external-ref\n",
        encoding="utf-8",
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok
    assert report.relationships_checked == 0
    assert ISSUE_TARGET_NOT_FOUND not in {i.code for i in report.issues}


# --- external-target verification references (ADR-096) ----------------------

_REQUIREMENT = "# {t}\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] r\n"


def test_verified_by_reference_is_never_broken(tmp_path):
    # A ## Verified By entry targets an external test/trace path, so like a
    # ticket it is exempt from referential integrity — never not-found, never
    # counted among resolved references (ADR-096).
    (tmp_path / "req-001.md").write_text(
        _REQUIREMENT.format(t="Cap") + "\n## Verified By\n\n- `tests/cap.spec.ts`\n",
        encoding="utf-8",
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok
    assert report.relationships_checked == 0
    assert ISSUE_TARGET_NOT_FOUND not in {i.code for i in report.issues}


def test_verified_by_on_non_requirement_is_unsupported(tmp_path):
    # `verified by` is requirement-only (capabilities, ADR-020); a decision
    # declaring it is an illegal edge (ADR-049 edge-legality).
    (tmp_path / "adr-001.md").write_text(
        _DECISION.format(t="A1") + "\n## Verified By\n\n- `tests/x.spec.ts`\n",
        encoding="utf-8",
    )
    report = validate_relationships(str(tmp_path))
    assert [i.code for i in report.issues] == [ISSUE_EDGE_UNSUPPORTED]
    issue = report.issues[0]
    assert issue.relationship == "verified_by"


def test_verified_by_on_requirement_is_supported(tmp_path):
    # A requirement MAY declare `verified by`; it must not be edge-unsupported.
    (tmp_path / "req-001.md").write_text(
        _REQUIREMENT.format(t="Cap") + "\n## Verified By\n\n- `tests/cap.spec.ts`\n",
        encoding="utf-8",
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok
    assert ISSUE_EDGE_UNSUPPORTED not in [i.code for i in report.issues]


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


# --- edge-legality / no silent drop (v0.14.0, ADR-049) ----------------------

_DESIGN = "# {t}\n\n## Context\n\nc\n\n## User Need\n\nn\n\n## Design\n\nd\n\n## Constraints\n\nk\n"


def test_unsupported_relationship_section_is_reported(tmp_path):
    # A design's schema does not declare `related designs`; today that section
    # is silently dropped. v0.14.0 surfaces it as a finding.
    (tmp_path / "a.md").write_text(_DESIGN.format(t="A"), encoding="utf-8")
    (tmp_path / "b.md").write_text(
        _DESIGN.format(t="B") + "\n## Related Designs\n\n- a\n", encoding="utf-8"
    )
    report = validate_relationships(str(tmp_path))
    assert not report.ok
    codes = [i.code for i in report.issues]
    assert codes.count(ISSUE_EDGE_UNSUPPORTED) == 1
    issue = next(i for i in report.issues if i.code == ISSUE_EDGE_UNSUPPORTED)
    assert issue.source_path.endswith("b.md")
    assert issue.relationship == "related_designs"
    # It is not counted as a resolved/broken reference — it produces no edge.
    assert report.relationships_checked == 0


def test_supersedes_on_non_decision_is_unsupported(tmp_path):
    # `supersedes` is decision-only; a roadmap declaring it is an illegal edge.
    (tmp_path / "v2.md").write_text(
        _ROADMAP.format(t="Two") + "\n## Supersedes\n\n- v1\n", encoding="utf-8"
    )
    report = validate_relationships(str(tmp_path))
    assert [i.code for i in report.issues] == [ISSUE_EDGE_UNSUPPORTED]


def test_supported_relationship_section_is_not_flagged(tmp_path):
    # A decision MAY declare `related decisions`; it must not be edge-unsupported.
    (tmp_path / "adr-001.md").write_text(_DECISION.format(t="A1"), encoding="utf-8")
    (tmp_path / "adr-002.md").write_text(
        _DECISION.format(t="A2") + "\n## Related Decisions\n\n- adr-001\n", encoding="utf-8"
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok
    assert ISSUE_EDGE_UNSUPPORTED not in [i.code for i in report.issues]


def test_unsupported_section_fails_cli(tmp_path):
    (tmp_path / "b.md").write_text(
        _DESIGN.format(t="B") + "\n## Related Designs\n\n- a\n", encoding="utf-8"
    )
    assert main(["relationships", str(tmp_path), "--validate"]) == 1


def test_unsupported_section_in_json_output(tmp_path, capsys):
    (tmp_path / "b.md").write_text(
        _DESIGN.format(t="B") + "\n## Related Designs\n\n- a\n", encoding="utf-8"
    )
    main(["relationships", str(tmp_path), "--validate", "--json"])
    payload = json.loads(capsys.readouterr().out)
    issue = next(i for i in payload["issues"] if i["code"] == ISSUE_EDGE_UNSUPPORTED)
    assert issue == {
        "source_path": issue["source_path"],
        "relationship": "related_designs",
        "code": ISSUE_EDGE_UNSUPPORTED,
    }
    assert "target" not in issue  # no resolved target for a structural finding


# --- status consistency / superseded targets (v0.14.1, ADR-049) -------------


def _decision(title, status, extra=""):
    return _DECISION.format(t=title) + f"\n## Status\n\n{status}\n" + extra


def test_reference_to_superseded_decision_is_reported(tmp_path):
    (tmp_path / "adr-001.md").write_text(_decision("Old", "Superseded"), encoding="utf-8")
    (tmp_path / "req-001.md").write_text(
        "# R\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] x\n\n"
        "## Related Decisions\n\n- adr-001\n",
        encoding="utf-8",
    )
    report = validate_relationships(str(tmp_path))
    assert not report.ok
    issue = next(i for i in report.issues if i.code == ISSUE_TARGET_SUPERSEDED)
    assert issue.source_path.endswith("req-001.md")
    assert issue.relationship == "related_decisions"
    assert issue.target == "adr-001"


def test_supersedes_edge_to_superseded_decision_is_allowed(tmp_path):
    # The replacing decision points at the one it supersedes — that is the one
    # edge allowed to reference a Superseded decision.
    (tmp_path / "adr-001.md").write_text(_decision("Old", "Superseded"), encoding="utf-8")
    (tmp_path / "adr-002.md").write_text(
        _decision("New", "Accepted", "\n## Supersedes\n\n- adr-001\n"), encoding="utf-8"
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok
    assert ISSUE_TARGET_SUPERSEDED not in [i.code for i in report.issues]


def test_deprecated_target_is_reported(tmp_path):
    (tmp_path / "adr-001.md").write_text(_decision("Old", "Deprecated"), encoding="utf-8")
    (tmp_path / "adr-002.md").write_text(
        _decision("Live", "Accepted", "\n## Related Decisions\n\n- adr-001\n"), encoding="utf-8"
    )
    report = validate_relationships(str(tmp_path))
    assert [i.code for i in report.issues] == [ISSUE_TARGET_SUPERSEDED]


def test_reference_to_achieved_roadmap_is_not_retired(tmp_path):
    # ADR-061: Achieved is a live terminal state (a delivered roadmap), so a
    # live artifact may reference it without a retired-target finding.
    (tmp_path / "v1.md").write_text(
        _ROADMAP.format(t="One") + "\n## Status\n\nAchieved\n", encoding="utf-8"
    )
    (tmp_path / "adr-001.md").write_text(
        _decision("Live", "Accepted", "\n## Related Roadmaps\n\n- v1\n"), encoding="utf-8"
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok
    assert ISSUE_TARGET_SUPERSEDED not in [i.code for i in report.issues]


def test_retired_source_reference_is_exempt(tmp_path):
    # A retired decision referencing another retired decision is a historical
    # chain, not live knowledge pointing at dead knowledge — not flagged.
    (tmp_path / "adr-001.md").write_text(_decision("Old", "Superseded"), encoding="utf-8")
    (tmp_path / "adr-002.md").write_text(
        _decision("Older", "Superseded", "\n## Related Decisions\n\n- adr-001\n"),
        encoding="utf-8",
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok


def test_accepted_target_is_not_flagged(tmp_path):
    (tmp_path / "adr-001.md").write_text(_decision("Live", "Accepted"), encoding="utf-8")
    (tmp_path / "adr-002.md").write_text(
        _decision("Also", "Accepted", "\n## Related Decisions\n\n- adr-001\n"), encoding="utf-8"
    )
    report = validate_relationships(str(tmp_path))
    assert report.ok


def test_superseded_target_fails_cli_with_suffix(tmp_path, capsys):
    (tmp_path / "adr-001.md").write_text(_decision("Old", "Superseded"), encoding="utf-8")
    (tmp_path / "req-001.md").write_text(
        "# R\n\n## Problem\n\np\n\n## Requirements\n\n- [REQ-001] x\n\n"
        "## Related Decisions\n\n- adr-001\n",
        encoding="utf-8",
    )
    assert main(["relationships", str(tmp_path), "--validate"]) == 1
    assert "✗ adr-001 superseded" in capsys.readouterr().out
