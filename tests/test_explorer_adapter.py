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


def test_open_ref_resolves_like_rac_resolve():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    lookup = adapter.open_ref("adr-001")
    assert lookup.message is None
    [row] = lookup.rows
    assert row.type == "decision"

    missing = adapter.open_ref("nope-999")
    assert missing.rows == ()
    assert missing.message is not None and "Not found" in missing.message


def test_open_ref_duplicates_offer_a_choice(tmp_path):
    doc = (
        "---\nschema_version: 1\nid: RAC-01JY4M8X2QZ7\ntype: decision\n---\n"
        "# A Decision\n\n## Context\n\nc\n\n## Decision\n\nd\n\n## Consequences\n\nq\n"
    )
    (tmp_path / "a.md").write_text(doc, encoding="utf-8")
    (tmp_path / "b.md").write_text(doc, encoding="utf-8")
    adapter = ExplorerAdapter(str(tmp_path))
    adapter.load()
    lookup = adapter.open_ref("RAC-01JY4M8X2QZ7")
    assert len(lookup.rows) == 2
    assert lookup.message is not None and "Duplicate" in lookup.message


def test_search_rows_rank_like_rac_find():
    adapter = ExplorerAdapter(str(FIXTURES / "all_types"))
    adapter.load()
    lookup = adapter.search_rows("md")
    assert lookup.rows  # path substring matches at minimum
    empty = adapter.search_rows("zzz-no-such-thing")
    assert empty.rows == ()
    assert empty.message is not None and "No matches" in empty.message


def test_search_rows_trailing_type_token_filters():
    adapter = ExplorerAdapter(str(FIXTURES / "all_types"))
    adapter.load()
    filtered = adapter.search_rows(". decision")
    assert filtered.rows
    assert all(row.type == "decision" for row in filtered.rows)


def test_browser_state_type_filter():
    adapter = ExplorerAdapter(str(FIXTURES / "all_types"))
    adapter.load()
    browser = adapter.browser_state("decision")
    assert browser is not None
    assert [group for group, _ in browser.groups] == ["decision"]
    assert browser.total == 1


def test_health_state_requires_a_load():
    assert ExplorerAdapter(str(FIXTURES / "valid_clean")).health_state() is None


def test_health_state_mirrors_portfolio_score():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    health = adapter.health_state()
    assert health is not None
    assert adapter.repository is not None
    assert health.score == adapter.repository.portfolio.health_score
    assert health.score_label  # text label beside the number


def test_health_state_lists_the_four_areas():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    health = adapter.health_state()
    assert health is not None
    assert [a.name for a in health.areas] == [
        "Completeness",
        "Relationships",
        "Validation",
        "Coverage",
    ]
    assert all(a.status_label and a.detail for a in health.areas)


def test_clean_repository_areas_are_healthy():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    health = adapter.health_state()
    assert health is not None
    by_name = {a.name: a for a in health.areas}
    assert by_name["Relationships"].status_label == "✓ Healthy"
    assert by_name["Validation"].status_label == "✓ Healthy"
    assert health.attention == ()


def test_broken_relationships_mark_the_relationships_area():
    adapter = ExplorerAdapter(str(FIXTURES / "broken_rels"))
    adapter.load()
    health = adapter.health_state()
    assert health is not None
    by_name = {a.name: a for a in health.areas}
    assert by_name["Relationships"].status_label == "! Needs Attention"
    assert "1 broken" in by_name["Relationships"].detail


def test_invalid_artifacts_mark_validation_as_error():
    adapter = ExplorerAdapter(str(FIXTURES / "invalid_known"))
    adapter.load()
    health = adapter.health_state()
    assert health is not None
    by_name = {a.name: a for a in health.areas}
    assert by_name["Validation"].status_label == "✗ Error"


def test_attention_items_link_to_artifacts_and_keep_priority():
    adapter = ExplorerAdapter(str(FIXTURES / "broken_rels"))
    adapter.load()
    health = adapter.health_state()
    assert health is not None
    assert adapter.repository is not None
    assert health.attention
    # Every attention row points at a real artifact (navigable to its context).
    paths = {a.path for a in adapter.repository.artifacts}
    assert all(row.path in paths for row in health.attention)
    # Order matches the portfolio's prioritized attention list verbatim.
    assert [row.message for row in health.attention] == [
        item.message for item in adapter.repository.portfolio.attention
    ]


def test_recommendations_state_requires_a_load():
    assert ExplorerAdapter(str(FIXTURES / "broken_rels")).recommendations_state() is None


def test_recommendations_mirror_core_review_findings():
    from rac.services.review import build_review

    adapter = ExplorerAdapter(str(FIXTURES / "broken_rels"))
    adapter.load()
    recs = adapter.recommendations_state()
    assert recs is not None
    report = build_review(str(FIXTURES / "broken_rels"))
    # One recommendation per Core review finding — Explorer invents none.
    assert recs.total == len(report.issues)


def test_recommendations_grouped_by_category_in_fixed_order():
    adapter = ExplorerAdapter(str(FIXTURES / "all_types"))
    adapter.load()
    recs = adapter.recommendations_state()
    assert recs is not None
    categories = [category for category, _ in recs.groups]
    order = ["Validation", "Relationships", "Repository Health", "Quality"]
    # Present categories appear in the fixed canonical order.
    assert categories == [c for c in order if c in categories]
    assert all(rows for _, rows in recs.groups)


def test_recommendations_explain_before_suggesting():
    adapter = ExplorerAdapter(str(FIXTURES / "broken_rels"))
    adapter.load()
    recs = adapter.recommendations_state()
    assert recs is not None
    rows = [r for _, group in recs.groups for r in group]
    rel = next(r for r in rows if r.category == "Relationships")
    assert rel.severity_label == "! Warning"
    assert rel.finding and rel.impact and rel.action
    assert "traceability" in rel.impact.lower()
    assert rel.path  # navigable to the affected artifact


def test_invalid_artifact_is_critical():
    adapter = ExplorerAdapter(str(FIXTURES / "invalid_known"))
    adapter.load()
    recs = adapter.recommendations_state()
    assert recs is not None
    rows = [r for _, group in recs.groups for r in group]
    validation = next(r for r in rows if r.category == "Validation")
    assert validation.severity_label == "✗ Critical"


def test_clean_repository_has_no_recommendations():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    recs = adapter.recommendations_state()
    assert recs is not None
    assert recs.total == 0
    assert recs.groups == ()


def test_import_preview_converts_markdown_without_writing(tmp_path):
    source = tmp_path / "notes.md"
    source.write_text("# Imported Notes\n\nbody\n", encoding="utf-8")
    target = tmp_path / "out.md"
    adapter = ExplorerAdapter(str(tmp_path))
    preview = adapter.import_preview(str(source), str(target))
    from rac.explorer.state import ImportPreview

    assert isinstance(preview, ImportPreview)
    assert preview.converter == "markdown"
    assert "# Imported Notes" in preview.markdown
    assert not target.exists()  # preview never writes (Initiative 4)


def test_import_preview_matches_rac_ingest(tmp_path):
    from rac.services.ingest import ingest

    source = tmp_path / "doc.md"
    source.write_text("# Same As Ingest\n", encoding="utf-8")
    preview = ExplorerAdapter(str(tmp_path)).import_preview(str(source))
    from rac.explorer.state import ImportPreview

    assert isinstance(preview, ImportPreview)
    assert preview.markdown == ingest(str(source)).markdown


def test_import_preview_reports_unsupported_type(tmp_path):
    source = tmp_path / "thing.xyz"
    source.write_text("data", encoding="utf-8")
    result = ExplorerAdapter(str(tmp_path)).import_preview(str(source))
    assert isinstance(result, str)
    assert "unsupported" in result.lower()


def test_import_preview_reports_missing_source(tmp_path):
    result = ExplorerAdapter(str(tmp_path)).import_preview(str(tmp_path / "nope.md"))
    assert isinstance(result, str)
    assert "could not read" in result.lower() or "no such" in result.lower()


def test_write_import_writes_and_refuses_overwrite(tmp_path):
    from rac.explorer.state import ImportPreview

    target = tmp_path / "written.md"
    preview = ImportPreview(
        source="src.md", converter="markdown", target=str(target), markdown="# Hi\n"
    )
    adapter = ExplorerAdapter(str(tmp_path))
    message = adapter.write_import(preview)
    assert "Imported" in message
    assert target.read_text(encoding="utf-8") == "# Hi\n"

    again = adapter.write_import(preview)
    assert "Refusing to overwrite" in again


def test_export_recommendations_renders_markdown_without_writing():
    from rac.explorer.state import ImportPreview

    adapter = ExplorerAdapter(str(FIXTURES / "broken_rels"))
    adapter.load()
    result = adapter.export_recommendations()
    assert isinstance(result, ImportPreview)
    assert result.converter == "export"
    assert "# Recommendations" in result.markdown
    assert "Impact:" in result.markdown and "Action:" in result.markdown


def test_export_recommendations_empty_when_clean():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    assert adapter.export_recommendations() == "No recommendations to export"


def test_relationships_view_outgoing_resolves_targets():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    assert adapter.repository is not None
    [req] = adapter.repository.artifacts_of_type("requirement")
    [adr] = adapter.repository.artifacts_of_type("decision")
    view = adapter.relationships_view(req.path)
    assert view is not None
    [link] = view.outgoing
    assert link.kind == "Related Decisions"
    assert link.navigable and link.target_path == adr.path


def test_relationships_view_impact_is_what_depends_on_this():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    assert adapter.repository is not None
    [req] = adapter.repository.artifacts_of_type("requirement")
    [adr] = adapter.repository.artifacts_of_type("decision")
    view = adapter.relationships_view(adr.path)
    assert view is not None
    assert view.outgoing == ()  # the ADR declares no outgoing references
    [dependent] = view.impact
    assert dependent.target_path == req.path
    assert dependent.navigable


def test_relationships_view_marks_unresolved_targets():
    adapter = ExplorerAdapter(str(FIXTURES / "broken_rels"))
    adapter.load()
    assert adapter.repository is not None
    [artifact] = adapter.repository.artifacts
    view = adapter.relationships_view(artifact.path)
    assert view is not None
    [link] = view.outgoing
    assert not link.navigable
    assert "✗" in link.label


def test_relationships_view_impact_matches_model():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    assert adapter.repository is not None
    for artifact in adapter.repository.artifacts:
        view = adapter.relationships_view(artifact.path)
        assert view is not None
        expected = {
            rel.source_path
            for rel in adapter.repository.relationships
            if rel.resolved_path == artifact.path
        }
        assert {link.target_path for link in view.impact} == expected


def test_relationships_view_requires_a_load():
    assert ExplorerAdapter(str(FIXTURES / "valid_clean")).relationships_view("x.md") is None


def test_cancelled_load_returns_none_not_an_error():
    token = CancellationToken()
    adapter = ExplorerAdapter(str(FIXTURES / "all_types"))

    def cancel_immediately(state: LoadProgressState) -> None:
        token.cancel()

    assert adapter.load(on_progress=cancel_immediately, cancel=token) is None
    assert adapter.repository is None
