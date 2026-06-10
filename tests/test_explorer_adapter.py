"""Tests for the Explorer adapter — service boundary without a TUI (v0.8.0)."""

from __future__ import annotations

from pathlib import Path

from rac.core.operations import CancellationToken
from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import LoadErrorState, LoadProgressState, RepositorySummaryState
from rac.services.portfolio import build_portfolio_summary

FIXTURES = Path(__file__).parent / "fixtures" / "portfolio_summary"


def test_load_returns_summary_state_from_core_numbers():
    directory = str(FIXTURES / "valid_clean")
    result = ExplorerAdapter(directory).load()

    assert isinstance(result, RepositorySummaryState)
    portfolio = build_portfolio_summary(directory)
    assert result.directory == directory
    assert result.artifact_total == portfolio.total_artifacts
    assert dict(result.by_type) == {t: c for t, c in portfolio.by_type.items() if c}
    assert result.relationship_total == portfolio.relationships.total
    assert result.broken_relationships == portfolio.relationships.broken
    assert result.health_score == portfolio.health_score
    assert result.error_count == 0
    assert result.warning_count == 0


def test_load_counts_diagnostics_by_severity():
    result = ExplorerAdapter(str(FIXTURES / "broken_rels")).load()
    assert isinstance(result, RepositorySummaryState)
    assert result.broken_relationships == 1
    assert result.warning_count >= 1


def test_load_keeps_repository_for_navigation():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    assert adapter.repository is None
    adapter.load()
    assert adapter.repository is not None
    assert adapter.repository.artifact("ADR-001") is not None


def test_load_translates_progress_with_labels():
    states: list[LoadProgressState] = []
    ExplorerAdapter(str(FIXTURES / "valid_clean")).load(on_progress=states.append)

    scan = [s for s in states if s.phase == "scan"]
    assert scan
    assert all("Scanning artifacts" in s.label for s in scan)
    assert f"({len(scan)}/{len(scan)})" in scan[-1].label
    assert [s.label for s in states if s.phase != "scan"] == [
        "Indexing artifacts",
        "Validating artifacts",
        "Analyzing relationships",
        "Calculating portfolio",
    ]


def test_failures_become_recoverable_error_state(tmp_path):
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    result = ExplorerAdapter(str(tmp_path)).load()
    assert isinstance(result, LoadErrorState)
    assert result.can_retry
    assert result.title == "Could not load repository"
    assert "UnicodeDecodeError" in result.detail


def test_empty_directory_is_a_summary_not_an_error(tmp_path):
    result = ExplorerAdapter(str(tmp_path)).load()
    assert isinstance(result, RepositorySummaryState)
    assert result.artifact_total == 0


def test_cancelled_load_returns_none_not_an_error():
    token = CancellationToken()
    adapter = ExplorerAdapter(str(FIXTURES / "all_types"))

    def cancel_immediately(state: LoadProgressState) -> None:
        token.cancel()

    assert adapter.load(on_progress=cancel_immediately, cancel=token) is None
    assert adapter.repository is None
