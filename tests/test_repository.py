"""Tests for the first-class repository model (v0.8.0)."""

from __future__ import annotations

from pathlib import Path

import pytest

from rac.core.operations import CancellationToken, OperationCancelled, Progress
from rac.services.index import build_repository_index
from rac.services.portfolio import build_portfolio_summary
from rac.services.relationships import ISSUE_TARGET_NOT_FOUND
from rac.services.repository import (
    SOURCE_RELATIONSHIPS,
    SOURCE_VALIDATION,
    load_repository,
)
from rac.services.validate import validate_directory

FIXTURES = Path(__file__).parent / "fixtures" / "portfolio_summary"


def load(subdir: str, **kwargs):
    return load_repository(str(FIXTURES / subdir), **kwargs)


# ---------------------------------------------------------------------------
# Composition: the model re-exposes the services, never re-derives them
# ---------------------------------------------------------------------------


def test_artifacts_match_repository_index():
    repo = load("all_types")
    index = build_repository_index(str(FIXTURES / "all_types"))
    assert [(a.id, a.type, a.title, a.path, list(a.aliases)) for a in repo.artifacts] == [
        (e.id, e.type, e.title, e.path, e.aliases) for e in index.artifacts
    ]


def test_statuses_match_directory_validation():
    repo = load("all_types")
    validation = validate_directory(str(FIXTURES / "all_types"))
    assert {a.path: a.status for a in repo.artifacts} == {
        f.path: f.status for f in validation.files
    }


def test_portfolio_matches_portfolio_summary():
    repo = load("valid_clean")
    summary = build_portfolio_summary(str(FIXTURES / "valid_clean"))
    assert repo.portfolio == summary
    assert repo.health_score == summary.health_score


def test_unknown_artifacts_are_included_and_skipped():
    repo = load("all_types")
    [unknown] = repo.artifacts_of_type("unknown")
    assert unknown.status == "skipped"


# ---------------------------------------------------------------------------
# Lookup surface for v0.8.1 navigation
# ---------------------------------------------------------------------------


def test_artifact_lookup_by_alias_is_casefolded():
    repo = load("valid_clean")
    adr = repo.artifact("adr-001")
    assert adr is not None
    assert adr.type == "decision"
    assert repo.artifact("ADR-001") == adr


def test_artifact_lookup_misses_return_none():
    repo = load("valid_clean")
    assert repo.artifact("no-such-artifact") is None


def test_artifacts_of_type_filters_in_walk_order():
    repo = load("all_types")
    types = {a.type for a in repo.artifacts}
    assert types == {"requirement", "decision", "roadmap", "prompt", "design", "unknown"}
    for artifact_type in types:
        subset = repo.artifacts_of_type(artifact_type)
        assert [a.path for a in subset] == [
            a.path for a in repo.artifacts if a.type == artifact_type
        ]


# ---------------------------------------------------------------------------
# Relationships: declared references with resolution outcomes
# ---------------------------------------------------------------------------


def test_resolved_relationship_links_source_to_target():
    repo = load("valid_clean")
    [rel] = repo.relationships
    assert rel.relationship == "related_decisions"
    assert rel.target == "ADR-001"
    assert rel.issue is None
    adr = repo.artifact("ADR-001")
    assert adr is not None
    assert rel.resolved_path == adr.path


def test_relationships_for_covers_both_endpoints():
    repo = load("valid_clean")
    [rel] = repo.relationships
    assert repo.relationships_for(rel.source_path) == [rel]
    assert rel.resolved_path is not None
    assert repo.relationships_for(rel.resolved_path) == [rel]


def test_broken_reference_carries_issue_code():
    repo = load("broken_rels")
    [rel] = repo.relationships
    assert rel.resolved_path is None
    assert rel.issue == ISSUE_TARGET_NOT_FOUND


# ---------------------------------------------------------------------------
# Diagnostics: unified findings, stable codes reused verbatim
# ---------------------------------------------------------------------------


def test_validation_errors_become_diagnostics():
    repo = load("invalid_known")
    [artifact] = repo.artifacts
    assert artifact.status == "invalid"
    diagnostics = repo.diagnostics_for(artifact.path)
    assert diagnostics
    assert all(d.source == SOURCE_VALIDATION for d in diagnostics)
    assert any(d.severity == "error" for d in diagnostics)
    assert all(d.identifier == artifact.id for d in diagnostics)


def test_broken_references_become_diagnostics():
    repo = load("broken_rels")
    [diag] = [d for d in repo.diagnostics if d.source == SOURCE_RELATIONSHIPS]
    assert diag.code == ISSUE_TARGET_NOT_FOUND
    assert diag.severity == "warning"
    assert "ADR-MISSING" in diag.message
    [artifact] = repo.artifacts
    assert diag.path == artifact.path
    assert diag.identifier == artifact.id


def test_clean_repository_has_no_diagnostics():
    repo = load("valid_clean")
    assert repo.diagnostics == []


# ---------------------------------------------------------------------------
# Operation interface: progress phases and cancellation
# ---------------------------------------------------------------------------


def test_load_reports_scan_then_analysis_phases():
    reports: list[Progress] = []
    repo = load("all_types", on_progress=reports.append)

    scan = [r for r in reports if r.phase == "scan"]
    assert [r.completed for r in scan] == list(range(1, len(repo.artifacts) + 1))

    analysis = [r.phase for r in reports if r.phase != "scan"]
    assert analysis == ["index", "validate", "relationships", "portfolio"]
    assert reports.index(scan[-1]) < reports.index(next(r for r in reports if r.phase == "index"))


def test_load_cancels_during_scan():
    token = CancellationToken()

    def cancel_immediately(progress: Progress) -> None:
        token.cancel()

    with pytest.raises(OperationCancelled):
        load("all_types", on_progress=cancel_immediately, cancel=token)


def test_load_respects_recursive_flag():
    nested = load_repository(str(FIXTURES), recursive=True)
    top_only = load_repository(str(FIXTURES), recursive=False)
    assert top_only.artifacts == []
    assert nested.artifacts
