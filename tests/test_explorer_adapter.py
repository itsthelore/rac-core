"""Tests for the Explorer adapter — service boundary without a TUI (v0.8.0)."""

from __future__ import annotations

from pathlib import Path

from rac.core.operations import CancellationToken
from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.preferences import Preferences
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


def test_failures_become_recoverable_error_state(tmp_path, monkeypatch):
    # A genuine, unexpected core failure surfaces as a recoverable error state.
    # The injection is at the load boundary because a malformed/non-UTF-8
    # artifact no longer aborts the load — WS4 degrades it gracefully.
    import rac.explorer.adapter as adapter_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("core exploded")

    monkeypatch.setattr(adapter_mod, "load_repository", _boom)
    result = ExplorerAdapter(str(tmp_path)).load()
    assert isinstance(result, LoadErrorState)
    assert result.can_retry
    assert result.title == "Could not load repository"
    assert "RuntimeError" in result.detail


def test_non_utf8_artifact_loads_gracefully_after_ws4(tmp_path):
    # WS4 (REQ-005): a non-UTF-8 artifact no longer crashes the load; the walk
    # continues and the file is surfaced as a (degraded) artifact, not a global
    # load error.
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    result = ExplorerAdapter(str(tmp_path)).load()
    assert isinstance(result, RepositorySummaryState)
    assert result.artifact_total == 1


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
    adapter.preferences = Preferences(artifact_grouping="type")
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
    assert unknown_rows[0].status_label == "– Unknown"


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


def test_artifact_markdown_returns_the_document_body(tmp_path):
    # The Content tab presents the knowledge itself: the Markdown body, with
    # the frontmatter stripped — identity already lives in the frame.
    body = "# ADR-001 Choose\n\n## Status\n\nAccepted\n\n## Context\n\nc\n\n## Decision\n\nd\n"
    (tmp_path / "adr-001.md").write_text(f"---\nschema_version: 1\n---\n\n{body}", encoding="utf-8")
    adapter = ExplorerAdapter(str(tmp_path))
    adapter.load()
    assert adapter.artifact_markdown(str(tmp_path / "adr-001.md")) == body


def test_artifact_markdown_without_frontmatter_is_unchanged():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    path = str(FIXTURES / "valid_clean" / "req-001.md")
    assert adapter.artifact_markdown(path) == Path(path).read_text(encoding="utf-8")


def test_resolve_link_by_reference_path_and_stem(tmp_path):
    (tmp_path / "adr-001.md").write_text(
        "# ADR-001 Choose\n\n## Status\n\nAccepted\n\n## Context\n\nc\n\n## Decision\n\nd\n",
        encoding="utf-8",
    )
    (tmp_path / "req-001.md").write_text(
        "# Search Feature\n\n## Problem\n\np\n\n## Requirements\n\n[REQ-001] shall work.\n",
        encoding="utf-8",
    )
    adapter = ExplorerAdapter(str(tmp_path))
    adapter.load()
    source = str(tmp_path / "req-001.md")
    target = str(tmp_path / "adr-001.md")

    assert adapter.resolve_link("adr-001", source) == target  # reference
    assert adapter.resolve_link("adr-001.md", source) == target  # relative path
    assert adapter.resolve_link("./adr-001.md#status", source) == target  # anchor stripped
    assert adapter.resolve_link("https://example.com/x", source) is None  # external
    assert adapter.resolve_link("nope.md", source) is None  # unresolvable


def test_artifact_markdown_unknown_path_returns_none():
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    adapter.load()
    assert adapter.artifact_markdown("nope.md") is None
    assert ExplorerAdapter(str(FIXTURES / "valid_clean")).artifact_markdown("x.md") is None


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
    # "all" is a token of every artifact's path (the all_types fixture dir); the
    # trailing "decision" filters to the one decision. Token-boundary matching
    # (ADR-037) replaced substring matching, so a punctuation-only query no
    # longer means "match everything" — the query must carry a real token.
    filtered = adapter.search_rows("all decision")
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


# --- the watcher fingerprint (v0.8.9) -----------------------------------------


def test_fingerprint_changes_on_edit_add_and_remove(tmp_path):
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    adapter = ExplorerAdapter(str(tmp_path))
    baseline = adapter.fingerprint()
    assert baseline is not None and len(baseline) == 1

    (tmp_path / "a.md").write_text("# A — edited\n", encoding="utf-8")
    edited = adapter.fingerprint()
    assert edited != baseline

    (tmp_path / "b.md").write_text("# B\n", encoding="utf-8")
    added = adapter.fingerprint()
    assert added != edited and len(added) == 2

    (tmp_path / "a.md").unlink()
    removed = adapter.fingerprint()
    assert removed != added and len(removed) == 1


def test_fingerprint_ignores_non_markdown_and_dotted_dirs(tmp_path):
    (tmp_path / "a.md").write_text("# A\n", encoding="utf-8")
    adapter = ExplorerAdapter(str(tmp_path))
    baseline = adapter.fingerprint()

    (tmp_path / "notes.txt").write_text("not an artifact", encoding="utf-8")
    hidden = tmp_path / ".cache"
    hidden.mkdir()
    (hidden / "c.md").write_text("# Hidden\n", encoding="utf-8")
    assert adapter.fingerprint() == baseline


# --- improvement suggestions (v0.8.9) ------------------------------------------


def _sparse_requirement(tmp_path: Path) -> Path:
    path = tmp_path / "req-sparse.md"
    path.write_text(
        "# Sparse Feature\n\n## Problem\n\nUsers cannot do the thing.\n\n"
        "## Requirements\n\n[REQ-001] Users can do the thing.\n",
        encoding="utf-8",
    )
    return path


def test_improvement_rows_render_missing_sections_with_guidance(tmp_path):
    path = _sparse_requirement(tmp_path)
    adapter = ExplorerAdapter(str(tmp_path))
    adapter.load()
    rows = adapter.improvement_rows(str(path))
    assert rows, "a sparse requirement should yield improvement suggestions"
    assert all(row.category == "Improvement" for row in rows)
    findings = {row.finding for row in rows}
    assert any("Success Metrics" in f for f in findings)
    assert all(row.action for row in rows)  # guidance question or fallback


def test_improvement_rows_empty_for_unknown_paths_and_before_load(tmp_path):
    path = _sparse_requirement(tmp_path)
    adapter = ExplorerAdapter(str(tmp_path))
    assert adapter.improvement_rows(str(path)) == ()  # before a load
    adapter.load()
    assert adapter.improvement_rows("elsewhere.md") == ()  # outside the load


# --- the directory tree (folders grouping, v0.8.10) -----------------------------


def _nested_repo(tmp_path: Path) -> Path:
    (tmp_path / "roadmaps" / "v1").mkdir(parents=True)
    (tmp_path / "decisions").mkdir()
    (tmp_path / "roadmaps" / "v1" / "a.md").write_text("# A\n", encoding="utf-8")
    (tmp_path / "decisions" / "b.md").write_text("# B\n", encoding="utf-8")
    (tmp_path / "c.md").write_text("# C\n", encoding="utf-8")
    return tmp_path


def test_folders_grouping_mirrors_the_directory_structure(tmp_path):
    adapter = ExplorerAdapter(str(_nested_repo(tmp_path)))
    adapter.load()
    browser = adapter.browser_state()
    assert browser is not None and browser.tree is not None  # the default mode
    root = browser.tree
    assert root.path == "" and [d.name for d in root.dirs] == ["decisions", "roadmaps"]
    assert [row.path for row in root.rows] == [str(tmp_path / "c.md")]
    roadmaps = root.dirs[1]
    assert roadmaps.path == "roadmaps" and [d.name for d in roadmaps.dirs] == ["v1"]
    v1 = roadmaps.dirs[0]
    assert v1.path == "roadmaps/v1"  # posix-pinned relpath: the dir: data key
    assert [row.path for row in v1.rows] == [str(tmp_path / "roadmaps" / "v1" / "a.md")]


def test_type_and_flat_groupings_carry_no_tree(tmp_path):
    adapter = ExplorerAdapter(str(_nested_repo(tmp_path)))
    adapter.load()
    for grouping in ("type", "flat"):
        adapter.preferences = Preferences(artifact_grouping=grouping)
        browser = adapter.browser_state()
        assert browser is not None and browser.tree is None


def test_type_rows_lists_one_type_for_browse(tmp_path):
    adapter = ExplorerAdapter(str(FIXTURES / "valid_clean"))
    assert adapter.type_rows("decision").message == "Repository not loaded yet"
    adapter.load()
    lookup = adapter.type_rows("decision")
    assert lookup.message is None and len(lookup.rows) == 1
    assert lookup.rows[0].type == "decision"
    empty = adapter.type_rows("nonsense")
    assert empty.rows == () and empty.message == "Nothing to browse: nonsense"


# --- artifact creation (/new, v0.8.10) ------------------------------------------


def test_new_preview_renders_the_template_without_writing(tmp_path):
    adapter = ExplorerAdapter(str(tmp_path))
    preview = adapter.new_preview("decision", str(tmp_path / "adr.md"))
    assert not isinstance(preview, str)
    assert "ID assigned on write" in preview.markdown
    assert "## Status" in preview.markdown  # the canonical template body
    assert preview.converter == "template"
    assert not (tmp_path / "adr.md").exists()  # preview never writes


def test_new_preview_reports_unknown_types(tmp_path):
    adapter = ExplorerAdapter(str(tmp_path))
    result = adapter.new_preview("nonsense", str(tmp_path / "x.md"))
    assert result == "Unknown artifact type: nonsense — try /schema"


def test_write_new_creates_through_core_with_a_minted_id(tmp_path):
    from rac.services.init import init_repository

    init_repository(str(tmp_path), key="RAC")
    adapter = ExplorerAdapter(str(tmp_path))
    target = tmp_path / "adr-demo.md"
    message = adapter.write_new("decision", str(target))
    assert message.startswith("Created ") and "RAC-" in message
    text = target.read_text(encoding="utf-8")
    assert text.startswith("---\n") and "id: RAC-" in text  # Core minted the ID


def test_write_new_refusals_write_nothing(tmp_path):
    from rac.services.init import init_repository

    init_repository(str(tmp_path), key="RAC")
    adapter = ExplorerAdapter(str(tmp_path))

    existing = tmp_path / "taken.md"
    existing.write_text("# Mine\n", encoding="utf-8")
    message = adapter.write_new("decision", str(existing))
    assert message == f"Refusing to overwrite existing file: {existing}"
    assert existing.read_text(encoding="utf-8") == "# Mine\n"

    missing_dir = tmp_path / "nowhere" / "adr.md"
    message = adapter.write_new("decision", str(missing_dir))
    assert "Directory does not exist" in message
    assert not missing_dir.exists()

    assert adapter.write_new("nonsense", str(tmp_path / "x.md")).startswith("Unknown artifact type")


def test_write_new_guides_uninitialized_repositories(tmp_path):
    adapter = ExplorerAdapter(str(tmp_path))
    message = adapter.write_new("decision", str(tmp_path / "adr.md"))
    assert "rac init" in message
    assert not (tmp_path / "adr.md").exists()


# --- portfolio stats (/stats, v0.8.10) -------------------------------------------


def test_stats_state_renders_the_dashboard_sections():
    fixtures = Path(__file__).parent / "fixtures"
    adapter = ExplorerAdapter(str(fixtures / "portfolio"))
    stats = adapter.stats_state()  # needs no loaded repository
    titles = [title for title, _ in stats.sections]
    assert titles[:2] == ["Overview", "Requirements & Quality"]
    lines = dict(stats.sections)["Overview"]
    assert any(line.startswith("Files found") for line in lines)
    assert any("Requirements" in line and "valid" in line for line in lines)
    quality = dict(stats.sections)["Requirements & Quality"]
    assert any(line.startswith("Requirements    7") for line in quality)
