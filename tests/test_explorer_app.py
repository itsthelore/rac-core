"""Headless tests for the Explorer workspace frame (v0.8.7, ADR-027).

Runs the Textual app through ``App.run_test()`` (no real terminal). Worker
results are awaited via ``app.workers.wait_for_complete()`` before asserting,
keeping the thread-worker tests deterministic. Key sequences are the
behaviour contract: they match what a user types.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from textual.widgets import Markdown, OptionList, Static, TabbedContent

from rac.explorer import firstrun, mascot
from rac.explorer.app import ExplorerApp
from rac.explorer.screens.main import MainScreen
from rac.explorer.widgets import RepositoryPanel
from rac.explorer.widgets.commandbar import CommandBar
from rac.explorer.widgets.sidebar import NavigationSidebar
from rac.explorer.widgets.views import ContextView

FIXTURES = Path(__file__).parent / "fixtures" / "portfolio_summary"


@pytest.fixture(autouse=True)
def onboarded_state(tmp_path_factory, monkeypatch):
    """Run every app test as a returning user; onboarding tests reset this."""
    state = tmp_path_factory.mktemp("xdg-state")
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    # Isolate preferences too (v0.8.6): never read or write the real user config.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg-config")))
    firstrun.mark_onboarded()
    return state


@pytest.fixture
def fresh_first_run(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "fresh-state"))


async def _settled_panel_text(app: ExplorerApp, pilot) -> str:
    await app.workers.wait_for_complete()
    await pilot.pause()
    return str(app.screen.query_one(RepositoryPanel).content)


async def _open_first_artifact(app: ExplorerApp, pilot) -> None:
    """Home → sidebar → expand the first group → open its first artifact."""
    await pilot.press("enter")  # home → sidebar
    await pilot.press("down", "enter")  # first type group → expand
    await pilot.pause()
    await pilot.press("down", "enter")  # first artifact → context view
    await pilot.pause()


# --- the shell: loading, summary, errors -------------------------------------


@pytest.mark.asyncio
async def test_shell_renders_repository_summary():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Artifacts   2" in text
        assert "requirement" in text and "decision" in text
        assert "Relationships  1" in text
        assert "Health         100 / 100  ✓ Healthy" in text


def test_summary_states_meaning_in_text_not_colour_alone():
    # DESIGN-visual-system: health carries a text label at every level.
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    assert app  # construction requires no terminal
    from rac.explorer.widgets import _health_label

    assert _health_label(90) == "✓ Healthy"
    assert _health_label(60) == "! Needs Attention"
    assert _health_label(10) == "✗ Unhealthy"


@pytest.mark.asyncio
async def test_broken_references_surface_in_summary():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "(1 broken)" in text
        assert "warnings" in text


@pytest.mark.asyncio
async def test_core_failure_renders_recoverable_error_state(tmp_path):
    (tmp_path / "bad.md").write_bytes(b"\xff\xfe not utf-8 \xff")
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "✗ Could not load repository" in text
        assert "Press r to retry." in text


@pytest.mark.asyncio
async def test_reload_binding_recovers_after_repair(tmp_path):
    bad = tmp_path / "bad.md"
    bad.write_bytes(b"\xff\xfe not utf-8 \xff")
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Could not load repository" in text

        bad.write_text("# Repaired Note\n", encoding="utf-8")
        await pilot.press("r")
        text = await _settled_panel_text(app, pilot)
        assert "Artifacts   1" in text


@pytest.mark.asyncio
async def test_home_shows_attention_and_hint():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Attention" in text
        assert "! 1 broken relationship" in text
        assert "Press / for anything" in text


# --- the persistent frame -----------------------------------------------------


@pytest.mark.asyncio
async def test_frame_persists_across_navigation():
    """Navigation swaps the context view; the frame widgets never rebuild."""
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        screen = app.screen
        assert isinstance(screen, MainScreen)
        sidebar = screen.query_one(NavigationSidebar)
        bar = screen.query_one(CommandBar)

        await pilot.press("h")  # → health view
        await pilot.pause()
        assert screen.current_view == "view-health"
        await pilot.press("escape")
        await pilot.pause()
        assert screen.current_view == "view-home"

        # Same screen, same widget instances — one stable frame.
        assert app.screen is screen
        assert screen.query_one(NavigationSidebar) is sidebar
        assert screen.query_one(CommandBar) is bar


@pytest.mark.asyncio
async def test_rac_lantern_theme_is_the_default():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        assert app.theme == "rac-lantern"


@pytest.mark.asyncio
async def test_theme_preference_overrides_the_default(monkeypatch, tmp_path):
    from rac.explorer.preferences import Preferences, save_preferences

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    save_preferences(Preferences(theme="textual-light"))
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        assert app.theme == "textual-light"


@pytest.mark.asyncio
async def test_sidebar_hides_in_narrow_terminals():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test(size=(70, 24)) as pilot:
        await _settled_panel_text(app, pilot)
        assert not app.screen.query_one(NavigationSidebar).display


def test_stylesheet_ships_as_package_data():
    # Breaks only in installed wheels unless pinned here: the stylesheet must
    # resolve through the package, not the source tree.
    from importlib.resources import files

    assert files("rac.explorer").joinpath("explorer.tcss").is_file()


# --- focus routing --------------------------------------------------------------


@pytest.mark.asyncio
async def test_slash_focuses_bar_and_esc_returns_focus():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")  # home → sidebar
        sidebar = app.screen.query_one(NavigationSidebar)
        assert app.focused is sidebar

        await pilot.press("/")
        assert isinstance(app.focused, CommandBar)
        await pilot.press("escape")
        await pilot.pause()
        assert app.focused is sidebar  # back to where the user was


@pytest.mark.asyncio
async def test_typing_q_in_the_bar_inserts_text_and_does_not_quit():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press("q")
        assert app.is_running
        assert app.screen.query_one(CommandBar).value == "q"
        # A typed `/` must also land in the input, not re-trigger the binding.
        await pilot.press("slash")
        assert app.screen.query_one(CommandBar).value == "q/"


@pytest.mark.asyncio
async def test_status_line_hints_follow_the_focused_panel():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        hints = app.screen.query_one("#status-hints", Static)
        await pilot.press("enter")  # sidebar focused
        await pilot.pause()
        sidebar_hints = str(hints.content)
        await pilot.press("/")  # bar focused
        await pilot.pause()
        bar_hints = str(hints.content)
        assert sidebar_hints != bar_hints
        assert "Run" in bar_hints

        # The health chip rides the right side after a load (text + number).
        right = str(app.screen.query_one("#status-right", Static).content)
        assert "✓ Healthy" in right and "100" in right
        assert "1 link" in right


# --- sidebar navigation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_sidebar_groups_carry_type_tags_and_counts():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        sidebar = app.screen.query_one(NavigationSidebar)
        labels = [str(node.label) for node in sidebar.root.children]
        assert any("Requirement" in label and "1" in label for label in labels)
        assert any("Decision" in label for label in labels)

        # Lazy population: rows appear on expand, tagged with text (ADR-028).
        sidebar.root.children[0].expand()
        await pilot.pause()
        row_label = str(sidebar.root.children[0].children[0].label)
        assert row_label.startswith("REQ ")
        assert "req-001" in row_label


@pytest.mark.asyncio
async def test_sidebar_enter_opens_context_and_esc_returns_home():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        assert app.screen.current_view == "view-context"
        text = str(app.screen.query_one("#context-panel", Static).content)
        assert "ID " in text and "Status " in text
        assert "Completeness  ✓ all recommended sections present" in text
        assert "Relationships" in text and "Diagnostics" in text
        # The selected artifact's status chip sits in the sidebar border.
        assert app.screen.query_one(NavigationSidebar).border_subtitle == "✓ valid"

        await pilot.press("escape")  # context → home (view history)
        await pilot.pause()
        assert app.screen.current_view == "view-home"


@pytest.mark.asyncio
async def test_flat_grouping_preference_lists_rows_without_headers(monkeypatch, tmp_path):
    from rac.explorer.preferences import Preferences, save_preferences

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    save_preferences(Preferences(artifact_grouping="flat"))
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        sidebar = app.screen.query_one(NavigationSidebar)
        # Rows directly under the root: every node carries an artifact path.
        assert sidebar.root.children
        assert all((node.data or "").endswith(".md") for node in sidebar.root.children)


@pytest.mark.asyncio
async def test_command_open_reveals_the_artifact_in_the_sidebar():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"open adr-001")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()  # reveal settles after a refresh
        sidebar = app.screen.query_one(NavigationSidebar)
        assert sidebar.cursor_node is not None
        assert (sidebar.cursor_node.data or "").endswith("adr-001.md")


# --- the tabbed context view ---------------------------------------------------------


@pytest.mark.asyncio
async def test_context_renders_the_artifact_markdown_by_default():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"open req-001")
        await pilot.press("enter")
        await pilot.pause()

        tabs = app.screen.query_one(TabbedContent)
        assert tabs.active == "tab-content"  # Notion content focus: the document first
        markdown = app.screen.query_one("#artifact-markdown", Markdown)
        source = (FIXTURES / "valid_clean" / "req-001.md").read_text(encoding="utf-8")
        assert markdown.source == source

        # The panel title carries the artifact identity.
        title = str(app.screen.query_one("#context-region").border_title)
        assert "req-001" in title and "Search Feature" in title


@pytest.mark.asyncio
async def test_context_tabs_carry_text_labels():
    # ADR-028: tab meaning rides on the label text, never colour alone.
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        tabs = app.screen.query_one(TabbedContent)
        labels = [
            str(tabs.get_tab(pane_id).label)
            for pane_id in ("tab-content", "tab-inspection", "tab-links", "tab-findings")
        ]
        assert labels == ["Content", "Inspection", "Links", "Findings"]


@pytest.mark.asyncio
async def test_links_tab_traverses_to_a_connected_artifact():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"open adr-001")
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("g")  # context → links tab
        await pilot.pause()
        assert app.screen.query_one(TabbedContent).active == "tab-links"
        panel = str(app.screen.query_one("#relationship-panel", Static).content)
        assert "Relationships" in panel and "Impact" in panel and "Lineage" in panel

        await pilot.press("enter")  # open the first connected artifact
        await pilot.pause()
        title = str(app.screen.query_one("#context-region").border_title)
        assert "req-001" in title  # traversed across the graph

        await pilot.press("escape")  # back through view history
        await pilot.pause()
        title = str(app.screen.query_one("#context-region").border_title)
        assert "adr-001" in title


@pytest.mark.asyncio
async def test_slash_relationships_opens_the_links_tab():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"relationships adr-001")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-context"
        assert app.screen.query_one(TabbedContent).active == "tab-links"


@pytest.mark.asyncio
async def test_context_e_opens_external_editor(monkeypatch):
    import rac.explorer.editor as editor_mod

    launched: list[list[str]] = []
    monkeypatch.setattr(editor_mod, "_RUNNER", lambda cmd: launched.append(list(cmd)))
    monkeypatch.setenv("EDITOR", "code")

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        await pilot.press("e")
        await pilot.pause()
        status = str(app.screen.query_one("#context-status", Static).content)
        assert "Opened" in status and "code" in status
        assert launched and launched[0][0] == "code"


@pytest.mark.asyncio
async def test_context_e_without_editor_shows_guidance(monkeypatch):
    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        await pilot.press("e")
        await pilot.pause()
        status = str(app.screen.query_one("#context-status", Static).content)
        assert "No editor configured" in status


# --- the command surface ----------------------------------------------------------


@pytest.mark.asyncio
async def test_slash_open_navigates_to_context():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        assert isinstance(app.focused, CommandBar)
        await pilot.press(*"open adr-001")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-context"
        text = str(app.screen.query_one("#context-panel", Static).content)
        assert "decision" in text


@pytest.mark.asyncio
async def test_slash_bare_text_searches_in_context_region_and_enter_opens():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        screen = app.screen
        await pilot.press("/")
        await pilot.press(*"search feature")
        await pilot.press("enter")
        await pilot.pause()
        # Results render inside the context region; the frame never jumps.
        assert app.screen is screen
        assert screen.current_view == "view-results"
        await pilot.press("enter")  # open the first (highlighted) result
        await pilot.pause()
        assert screen.current_view == "view-context"


@pytest.mark.asyncio
async def test_slash_help_lists_registry():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"help")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-results"
        results = app.screen.query_one("#command-results", OptionList)
        assert results.option_count == 12  # the whole registry, nothing more


@pytest.mark.asyncio
async def test_slash_home_returns_to_the_home_view():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        await pilot.press("/")
        await pilot.press(*"home")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-home"


@pytest.mark.asyncio
async def test_slash_browse_with_type_filter_focuses_the_group():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"browse decision")
        await pilot.press("enter")
        await pilot.pause()
        sidebar = app.screen.query_one(NavigationSidebar)
        assert app.focused is sidebar
        assert sidebar.cursor_node is not None
        assert sidebar.cursor_node.data == "group:decision"
        assert sidebar.cursor_node.is_expanded


@pytest.mark.asyncio
async def test_slash_preferences_shows_values_and_path():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"preferences")
        await pilot.press("enter")
        await pilot.pause()
        results = app.screen.query_one("#command-results", OptionList)
        rendered = " ".join(str(opt.prompt) for opt in results._options)
        assert "mascot" in rendered and "explorer.json" in rendered


# --- onboarding -------------------------------------------------------------------


def test_first_run_marker_round_trip(fresh_first_run):
    assert firstrun.is_first_run()
    firstrun.mark_onboarded()
    assert not firstrun.is_first_run()


@pytest.mark.asyncio
async def test_first_run_shows_onboarding_then_enter_continues(fresh_first_run):
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Welcome to RAC Explorer" in text
        assert "Repository found" in text
        assert "✓ relationships  1" in text
        assert "/      search and commands" in text

        await pilot.press("enter")
        await pilot.pause()
        text = str(app.screen.query_one(RepositoryPanel).content)
        assert "Health" in text  # the normal summary
    assert not firstrun.is_first_run()  # marker written


@pytest.mark.asyncio
async def test_returning_users_skip_onboarding():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Welcome to RAC Explorer" not in text
        assert "Health" in text


@pytest.mark.asyncio
async def test_first_run_empty_repository_teaches(fresh_first_run, tmp_path):
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "No RAC artifacts found." in text
        assert "rac new" in text and "rac ingest" in text


@pytest.mark.asyncio
async def test_first_run_invalid_repository_opens_anyway(fresh_first_run):
    app = ExplorerApp(str(FIXTURES / "invalid_known"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Repository issues found" in text
        assert "✗ 1 validation errors" in text
        assert "Press Enter to open anyway" in text

        await pilot.press("enter")
        await pilot.pause()
        text = str(app.screen.query_one(RepositoryPanel).content)
        assert "Health" in text


@pytest.mark.asyncio
async def test_first_run_welcome_shows_mascot_when_enabled(fresh_first_run):
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert mascot.label(mascot.DISCOVERY) in text  # mascot present by default


@pytest.mark.asyncio
async def test_mascot_can_be_disabled(fresh_first_run, tmp_path, monkeypatch):
    from rac.explorer.preferences import Preferences, save_preferences

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    save_preferences(Preferences(mascot=False))
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert mascot.label(mascot.DISCOVERY) not in text  # disabling loses the art
        assert "Repository found" in text  # but no information is lost


# --- health and recommendations ----------------------------------------------------


@pytest.mark.asyncio
async def test_h_binding_opens_health_view():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")
        await pilot.pause()
        assert app.screen.current_view == "view-health"
        overview = str(app.screen.query_one("#health-overview", Static).content)
        assert "Score" in overview
        assert "Completeness" in overview and "Coverage" in overview
        assert "✓ Healthy" in overview
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.current_view == "view-home"


@pytest.mark.asyncio
async def test_slash_health_opens_health_view():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"health")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-health"


@pytest.mark.asyncio
async def test_health_attention_item_opens_context():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")
        await pilot.pause()
        await pilot.press("enter")  # first attention item (highlighted)
        await pilot.pause()
        assert app.screen.current_view == "view-context"


@pytest.mark.asyncio
async def test_slash_recommendations_opens_view():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"recommendations")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-recommendations"
        listing = app.screen.query_one("#recommendations-list", OptionList)
        assert listing.option_count >= 1  # at least the broken-relationship finding


@pytest.mark.asyncio
async def test_health_r_opens_recommendations_and_item_opens_context():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")
        await pilot.pause()
        await pilot.press("r")  # health → recommendations
        await pilot.pause()
        assert app.screen.current_view == "view-recommendations"
        await pilot.press("enter")  # first recommendation → its artifact
        await pilot.pause()
        assert app.screen.current_view == "view-context"


@pytest.mark.asyncio
async def test_findings_tab_shows_the_artifacts_findings():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")
        await pilot.pause()
        await pilot.press("enter")  # the affected artifact's context view
        await pilot.pause()
        findings = str(app.screen.query_one("#findings-panel", Static).content)
        assert "Impact:" in findings and "Action:" in findings


# --- import and export ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_slash_import_previews_then_confirms_write(tmp_path):
    source = tmp_path / "incoming.md"
    source.write_text("# Imported Doc\n\nhello\n", encoding="utf-8")
    target = tmp_path / "result.md"

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*f"import {source} {target}")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.screen.current_view == "view-import"
        panel = str(app.screen.query_one("#import-panel", Static).content)
        assert "Preview" in panel and "Imported Doc" in panel
        assert not target.exists()  # not written until confirmed

        await pilot.press("y")
        await pilot.pause()
        assert target.read_text(encoding="utf-8") == "# Imported Doc\n\nhello\n"
        assert "Imported" in str(app.screen.query_one("#import-panel", Static).content)


@pytest.mark.asyncio
async def test_slash_import_cancel_writes_nothing(tmp_path):
    source = tmp_path / "incoming.md"
    source.write_text("# Doc\n", encoding="utf-8")
    target = tmp_path / "result.md"

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*f"import {source} {target}")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert app.screen.current_view == "view-import"
        await pilot.press("escape")  # cancel before confirming
        await pilot.pause()
        assert app.screen.current_view == "view-home"
        assert not target.exists()


@pytest.mark.asyncio
async def test_slash_import_reports_unsupported(tmp_path):
    source = tmp_path / "thing.xyz"
    source.write_text("x", encoding="utf-8")

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*f"import {source}")
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        panel = str(app.screen.query_one("#import-panel", Static).content)
        assert "Import failed" in panel


@pytest.mark.asyncio
async def test_recommendations_export_previews_then_writes(tmp_path, monkeypatch):
    from rac.explorer.screens.confirm import ConfirmWriteScreen

    monkeypatch.chdir(tmp_path)  # export defaults to recommendations.md in cwd
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")
        await pilot.pause()
        await pilot.press("r")  # recommendations
        await pilot.pause()
        await pilot.press("x")  # export → the confirm-write modal
        await pilot.pause()
        assert isinstance(app.screen, ConfirmWriteScreen)
        assert not (tmp_path / "recommendations.md").exists()  # preview only

        # The modal speaks the frame's language: a titled panel and key chips.
        dialog = app.screen.query_one("#confirm-dialog")
        assert "recommendations.md" in str(dialog.border_title)
        chips = str(app.screen.query_one("#confirm-chips", Static).content)
        assert "Confirm" in chips and "Cancel" in chips

        await pilot.press("y")
        await pilot.pause()
        written = (tmp_path / "recommendations.md").read_text(encoding="utf-8")
        assert "# Recommendations" in written
        assert "Imported" in str(app.screen.query_one("#confirm-panel", Static).content)
        await pilot.press("escape")  # the modal pops; the frame is still there
        await pilot.pause()
        assert isinstance(app.screen, MainScreen)


# --- continuity ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_reopens_last_artifact():
    directory = str(FIXTURES / "valid_clean")
    # First session: open an artifact (records it), then quit.
    app = ExplorerApp(directory)
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        assert app.screen.current_view == "view-context"
        recorded = app.screen.query_one(ContextView).context.path
        await pilot.press("q")

    # Second session on the same repository: resume via `.`.
    app2 = ExplorerApp(directory)
    async with app2.run_test() as pilot:
        await _settled_panel_text(app2, pilot)
        assert app2.screen.current_view == "view-home"
        await pilot.press("full_stop")
        await pilot.pause()
        assert app2.screen.current_view == "view-context"
        assert app2.screen.query_one(ContextView).context.path == recorded


@pytest.mark.asyncio
async def test_remains_responsive_at_repository_scale(tmp_path):
    # Initiative 6: re-validate the 1000+ artifact target against the tree.
    root = tmp_path / "large"
    root.mkdir()
    for i in range(600):
        (root / f"adr-{i:04d}.md").write_text(
            f"# ADR-{i:04d} D{i}\n\n## Status\n\nAccepted\n\n## Context\n\nc\n\n"
            "## Decision\n\nd\n\n## Consequences\n\nq\n",
            encoding="utf-8",
        )
    for i in range(600):
        (root / f"req-{i:04d}.md").write_text(
            f"# Feature {i}\n\n## Problem\n\np\n\n## Requirements\n\n"
            f"[REQ-{i:04d}] shall work.\n\n## Related Decisions\n\n- ADR-{i % 600:04d}\n",
            encoding="utf-8",
        )

    started = time.monotonic()
    app = ExplorerApp(str(root))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Artifacts   1200" in text
        # The sidebar mounts groups lazily; expanding one renders 600 rows.
        sidebar = app.screen.query_one(NavigationSidebar)
        sidebar.root.children[0].expand()
        await pilot.pause()
        assert len(sidebar.root.children[0].children) == 600
    assert time.monotonic() - started < 60  # generous ceiling; catch regressions


@pytest.mark.asyncio
async def test_quit_binding_exits_cleanly():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("q")
    assert not app.is_running
