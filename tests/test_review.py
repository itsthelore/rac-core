"""Tests for rac.services.review and the ``rac review`` CLI command (v0.7.9)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rac.cli import main
from rac.services.portfolio import build_portfolio_summary
from rac.services.review import (
    PRIORITY_BROKEN_RELATIONSHIP,
    PRIORITY_INVALID_ARTIFACT,
    PRIORITY_MISSING_RECOMMENDED,
    PRIORITY_UNKNOWN_ARTIFACT,
    REVIEW_UNKNOWN_ARTIFACT,
    build_review,
    review_from_portfolio,
)

FIXTURES = Path(__file__).parent / "fixtures" / "portfolio_summary"


def review(subdir: str, **kwargs):
    return build_review(str(FIXTURES / subdir), **kwargs)


def test_review_from_portfolio_matches_build_review():
    # v0.8.3 seam: the same review, built from an already-computed portfolio.
    for subdir in ("invalid_known", "broken_rels", "valid_clean", "all_types"):
        directory = str(FIXTURES / subdir)
        portfolio = build_portfolio_summary(directory)
        assert review_from_portfolio(directory, portfolio).to_dict() == (
            build_review(directory).to_dict()
        )


# ---------------------------------------------------------------------------
# Priority mapping (REQ-Repository-Review-Mode: issues ordered by impact)
# ---------------------------------------------------------------------------


def test_invalid_artifact_is_priority_one():
    r = review("invalid_known")
    assert r.issues[0].priority == PRIORITY_INVALID_ARTIFACT
    assert r.issues[0].code == "invalid-artifact"
    assert r.issues[0].severity == "error"
    assert not r.ok


def test_broken_relationship_is_priority_two():
    r = review("broken_rels")
    assert any(i.priority == PRIORITY_BROKEN_RELATIONSHIP for i in r.issues)
    assert not r.ok


def test_unknown_artifact_is_priority_three_and_advisory():
    r = review("unknown_only")
    assert len(r.issues) == 1
    issue = r.issues[0]
    assert issue.priority == PRIORITY_UNKNOWN_ARTIFACT
    assert issue.code == REVIEW_UNKNOWN_ARTIFACT
    assert issue.severity == "info"
    assert "rac inspect" in issue.action
    assert r.ok  # advisory: unknown alone never fails a review


def test_missing_recommended_is_priority_four():
    r = review("valid_clean")
    # valid_clean artifacts are complete; all_types includes incomplete ones
    assert all(i.priority != PRIORITY_MISSING_RECOMMENDED for i in r.issues)
    r = review("all_types")
    assert any(i.priority == PRIORITY_MISSING_RECOMMENDED for i in r.issues)


def test_issues_sorted_by_priority_then_path():
    r = review("all_types")
    keys = [(i.priority, i.path, i.code) for i in r.issues]
    assert keys == sorted(keys)


def test_clean_repository_reviews_ok():
    r = review("valid_clean")
    assert r.ok
    assert r.issues == []
    assert r.actions == []


# ---------------------------------------------------------------------------
# Actions: deterministic, deduplicated, priority order
# ---------------------------------------------------------------------------


def test_actions_follow_issue_priority_and_dedupe():
    r = review("invalid_known")
    assert r.actions[0].startswith("Run: rac validate ")
    assert len(r.actions) == len(set(r.actions))


def test_every_issue_carries_an_action():
    r = review("all_types")
    assert all(i.action for i in r.issues)


# ---------------------------------------------------------------------------
# CLI: exit codes (0 ok / 1 priority 1-2 issues / 2 usage)
# ---------------------------------------------------------------------------


def test_cli_clean_exits_zero(capsys):
    assert main(["review", str(FIXTURES / "valid_clean")]) == 0


def test_cli_invalid_artifact_exits_one(capsys):
    assert main(["review", str(FIXTURES / "invalid_known")]) == 1


def test_cli_broken_relationships_exit_one(capsys):
    assert main(["review", str(FIXTURES / "broken_rels")]) == 1


def test_cli_advisory_issues_exit_zero(capsys):
    assert main(["review", str(FIXTURES / "unknown_only")]) == 0


def test_cli_not_a_directory_exits_two(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["review", str(FIXTURES / "does_not_exist")])
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# CLI: human output
# ---------------------------------------------------------------------------


def test_cli_human_output_sections(capsys):
    main(["review", str(FIXTURES / "invalid_known")])
    out = capsys.readouterr().out
    assert "Repository Review" in out
    assert "Validation" in out
    assert "Relationships" in out
    assert "Priority 1 — Invalid artifacts" in out
    assert "Suggested Actions" in out
    assert "Health Score" in out


def test_cli_human_output_clean(capsys):
    main(["review", str(FIXTURES / "valid_clean")])
    out = capsys.readouterr().out
    assert "Nothing needs attention" in out
    assert "Suggested Actions" not in out


# ---------------------------------------------------------------------------
# CLI: JSON contract (ADR-007 — stable, schema_version-gated)
# ---------------------------------------------------------------------------


def test_cli_json_contract(capsys):
    rc = main(["review", str(FIXTURES / "all_types"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "1"
    assert payload["recursive"] is True
    assert set(payload) == {
        "schema_version",
        "directory",
        "recursive",
        "ok",
        "artifacts",
        "validation",
        "relationships",
        "health",
        "issues",
        "actions",
    }
    assert payload["artifacts"]["total"] == 6
    assert payload["artifacts"]["by_type"]["unknown"] == 1
    assert len(payload["artifacts"]["unknown_paths"]) == 1
    for issue in payload["issues"]:
        assert set(issue) == {
            "priority",
            "severity",
            "path",
            "identifier",
            "code",
            "message",
            "action",
            "impact",
        }
        assert issue["impact"]  # Core-owned, always present (v0.8.11)
    assert rc in (0, 1)


def test_cli_json_ok_matches_exit_code(capsys):
    rc = main(["review", str(FIXTURES / "invalid_known"), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert rc == 1


# ---------------------------------------------------------------------------
# Recursion control
# ---------------------------------------------------------------------------


def test_top_level_flag(capsys):
    portfolio_dir = Path(__file__).parent / "fixtures" / "portfolio"
    rc = main(["review", str(portfolio_dir), "--top-level", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["recursive"] is False
    assert payload["artifacts"]["total"] == 3  # sub/feature_c.md excluded
    assert rc == 1  # broken.md is invalid


def test_empty_directory_reviews_ok(tmp_path, capsys):
    assert main(["review", str(tmp_path)]) == 0
    assert "Nothing needs attention" in capsys.readouterr().out


def test_impact_is_core_owned_and_always_present():
    # v0.8.11: the "why it matters" sentence is repository intelligence,
    # not viewer copy — every consumer reads the same text.
    from rac.services.review import impact_for

    report = build_review(str(FIXTURES / "invalid_known"))
    assert report.issues
    for issue in report.issues:
        assert issue.impact == impact_for(issue.code)
    assert impact_for("some-future-code") == "This finding affects repository quality."
