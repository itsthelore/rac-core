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


def test_summary_attention_lines_aggregate_findings():
    result = ExplorerAdapter(str(FIXTURES / "broken_rels")).load()
    assert isinstance(result, RepositorySummaryState)
    assert "1 broken relationship" in result.attention

    clean = ExplorerAdapter(str(FIXTURES / "valid_clean")).load()
    assert isinstance(clean, RepositorySummaryState)
    assert clean.attention == ()


def test_browser_state_requires_a_load():
    assert ExplorerAdapter(str(FIXTURES / "all_types")).browser_state() is None


def test_browser_state_groups_by_type_in_walk_order():
    adapter = ExplorerAdapter(str(FIXTURES / "all_types"))
    adapter.load()
    browser = adapter.browser_state()
    assert browser is not None
    assert browser.total == 6
    assert [group for group, _ in browser.groups] == [
        "requirement",
        "decision",
        "roadmap",
        "prompt",
        "design",
        "unknown",
    ]
    assert all(rows for _, rows in browser.groups)
    [unknown_rows] = [rows for group, rows in browser.groups if group == "unknown"]
    assert unknown_rows[0].status_label == "– unknown"


def test_context_state_renders_resolved_and_incoming_relationships():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    assert adapter.repository is not None
    [req] = adapter.repository.artifacts_of_type("requirement")
    [adr] = adapter.repository.artifacts_of_type("decision")

    req_context = adapter.context_state(req.path)
    assert req_context is not None
    [outgoing] = req_context.outgoing
    assert outgoing.startswith("Related Decisions → ADR-001")
    assert (adr.title or "") in outgoing
    assert req_context.incoming == ()
    assert req_context.diagnostics == ()

    adr_context = adapter.context_state(adr.path)
    assert adr_context is not None
    assert adr_context.outgoing == ()
    [incoming] = adr_context.incoming
    assert incoming.startswith("← ")
    assert "Related Decisions" in incoming


def test_context_state_marks_broken_references():
    adapter = ExplorerAdapter(str(FIXTURES / "broken_rels"))
    adapter.load()
    assert adapter.repository is not None
    [artifact] = adapter.repository.artifacts
    context = adapter.context_state(artifact.path)
    assert context is not None
    [outgoing] = context.outgoing
    assert "ADR-MISSING" in outgoing
    assert "✗ relationship target not found" in outgoing
    assert any("warning" in line for line in context.diagnostics)


def test_context_state_unknown_path_returns_none():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    assert adapter.context_state("nope.md") is None


def test_cancelled_load_returns_none_not_an_error():
    token = CancellationToken()
    adapter = ExplorerAdapter(str(FIXTURES / "all_types"))

    def cancel_immediately(state: LoadProgressState) -> None:
        token.cancel()

    assert adapter.load(on_progress=cancel_immediately, cancel=token) is None
    assert adapter.repository is None
