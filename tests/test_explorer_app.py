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
from textual.widgets import Input, Markdown, OptionList, Static, TabbedContent

from rac.explorer import commands, firstrun, mascot
from rac.explorer.app import ExplorerApp
from rac.explorer.screens.main import MainScreen
from rac.explorer.widgets import RepositoryPanel
from rac.explorer.widgets.palette import CommandPalette
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
    """Home → sidebar → open the first artifact leaf.

    Fixture repositories keep artifacts at the root, so the folders default
    (v0.8.10) renders them as top-level leaves.
    """
    await pilot.press("enter")  # home → sidebar
    await pilot.press("down", "enter")  # first artifact leaf → context view
    await pilot.pause()


# --- the shell: loading, summary, errors -------------------------------------


@pytest.mark.asyncio
async def test_shell_renders_repository_summary():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Artifacts      2" in text
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
async def test_core_failure_renders_recoverable_error_state(tmp_path, monkeypatch):
    # A genuine core failure renders the recoverable error screen. WS4 makes a
    # malformed/non-UTF-8 artifact degrade gracefully, so the failure is injected
    # at the load boundary rather than via bad file content.
    import rac.explorer.adapter as adapter_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("core exploded")

    monkeypatch.setattr(adapter_mod, "load_repository", _boom)
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "✗ Could not load repository" in text
        assert "Press r to retry." in text


@pytest.mark.asyncio
async def test_reload_binding_recovers_after_repair(tmp_path, monkeypatch):
    import rac.explorer.adapter as adapter_mod

    real_load = adapter_mod.load_repository
    state = {"broken": True}

    def _maybe(*args, **kwargs):
        if state["broken"]:
            raise RuntimeError("core exploded")
        return real_load(*args, **kwargs)

    monkeypatch.setattr(adapter_mod, "load_repository", _maybe)
    (tmp_path / "note.md").write_text("# Repaired Note\n", encoding="utf-8")
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Could not load repository" in text

        state["broken"] = False  # the operator repairs the underlying failure
        await pilot.press("r")
        text = await _settled_panel_text(app, pilot)
        assert "Artifacts      1" in text


@pytest.mark.asyncio
async def test_home_shows_attention_and_hint():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Attention" in text
        assert "! 1 broken relationship" in text
        # The key hints live in the status-line chips, not panel text (v0.8.8).
        assert "Press / for anything" not in text


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
        palette = screen.query_one(CommandPalette)

        await pilot.press("h")  # → health view
        await pilot.pause()
        assert screen.current_view == "view-health"
        await pilot.press("escape")
        await pilot.pause()
        assert screen.current_view == "view-home"

        # Same screen, same widget instances — one stable frame.
        assert app.screen is screen
        assert screen.query_one(NavigationSidebar) is sidebar
        assert screen.query_one(CommandPalette) is palette


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


# --- focus routing and the palette ------------------------------------------------


@pytest.mark.asyncio
async def test_slash_summons_palette_and_esc_restores_focus():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        palette = app.screen.query_one(CommandPalette)
        assert not palette.display  # the idle frame carries no input chrome

        await pilot.press("enter")  # home → sidebar
        sidebar = app.screen.query_one(NavigationSidebar)
        assert app.focused is sidebar

        await pilot.press("/")
        assert palette.display
        assert isinstance(app.focused, Input)
        # Empty input teaches: the whole registry, first row highlighted.
        menu = palette.query_one("#palette-menu", OptionList)
        assert menu.option_count == len(commands.REGISTRY)
        assert menu.highlighted == 0

        await pilot.press("escape")
        await pilot.pause()
        assert not palette.display
        assert app.focused is sidebar  # back to where the user was


@pytest.mark.asyncio
async def test_typing_q_in_the_palette_inserts_text_and_does_not_quit():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press("q")
        assert app.is_running
        field = app.screen.query_one("#command-input", Input)
        assert field.value == "q"
        # A typed `/` must also land in the input, not re-trigger the binding.
        await pilot.press("slash")
        assert field.value == "q/"


@pytest.mark.asyncio
async def test_palette_filters_commands_and_enter_completes_them():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"op")  # a strict prefix of /open
        await pilot.pause()
        palette = app.screen.query_one(CommandPalette)
        menu = palette.query_one("#palette-menu", OptionList)
        assert menu.option_count == 1

        await pilot.press("enter")  # completes the arg-taking command
        await pilot.pause()
        field = app.screen.query_one("#command-input", Input)
        assert field.value == "open "
        assert palette.display  # still open, waiting for the argument

        await pilot.press(*"req-001")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-context"


@pytest.mark.asyncio
async def test_palette_arrows_drive_menu_while_typing_continues():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        palette = app.screen.query_one(CommandPalette)
        menu = palette.query_one("#palette-menu", OptionList)
        assert menu.highlighted == 0
        await pilot.press("down")
        assert menu.highlighted == 1
        assert isinstance(app.focused, Input)  # focus never left the input
        await pilot.press("up")
        assert menu.highlighted == 0


@pytest.mark.asyncio
async def test_palette_quick_opens_a_matching_artifact():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"elasticsearch")  # not a command — live matches
        await pilot.pause()
        palette = app.screen.query_one(CommandPalette)
        menu = palette.query_one("#palette-menu", OptionList)
        first = menu.get_option_at_index(0)
        assert (first.id or "").startswith("path:")

        await pilot.press("enter")  # quick-open the highlighted match
        await pilot.pause()
        assert app.screen.current_view == "view-context"
        title = str(app.screen.query_one("#context-region").border_title)
        assert "adr-001" in title


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
    from rac.explorer.preferences import Preferences, save_preferences

    save_preferences(Preferences(artifact_grouping="type"))
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        sidebar = app.screen.query_one(NavigationSidebar)
        labels = [str(node.label) for node in sidebar.root.children]
        assert any("Requirement" in label and "1" in label for label in labels)
        assert any("Decision" in label for label in labels)

        # Lazy population: rows appear on expand, tagged with text (ADR-028).
        # The human title leads; the opaque ID lives in the context panel.
        sidebar.root.children[0].expand()
        await pilot.pause()
        row_label = str(sidebar.root.children[0].children[0].label)
        assert row_label.startswith("REQ ")
        assert "Search Feature" in row_label
        assert "req-001" not in row_label


@pytest.mark.asyncio
async def test_sidebar_marks_invalid_artifacts():
    app = ExplorerApp(str(FIXTURES / "invalid_known"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        sidebar = app.screen.query_one(NavigationSidebar)
        # Folders default: root-level artifacts render as top-level leaves.
        labels = [str(node.label) for node in sidebar.root.children]
        assert any("✗" in label for label in labels)  # trouble visible from the tree


@pytest.mark.asyncio
async def test_sidebar_keeps_expansion_and_cursor_across_reload():
    from rac.explorer.preferences import Preferences, save_preferences

    save_preferences(Preferences(artifact_grouping="type"))  # lazy-population coverage
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")  # focus sidebar
        await pilot.press("down", "enter")  # expand the first group
        await pilot.pause()
        await pilot.press("down")  # cursor onto the first artifact row
        await pilot.pause()
        sidebar = app.screen.query_one(NavigationSidebar)
        cursor_data = sidebar.cursor_node.data

        await pilot.press("r")  # reload rebuilds the tree
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.pause()
        assert sidebar.root.children[0].is_expanded  # the group stayed open
        assert sidebar.cursor_node is not None
        assert sidebar.cursor_node.data == cursor_data  # same row under the cursor


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
        assert app.screen.query_one(NavigationSidebar).border_subtitle == "✓ Valid"

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
async def test_content_pane_takes_focus_and_scrolls(tmp_path):
    from textual.containers import VerticalScroll

    # A document long enough to overflow the pane.
    body = "# Long Doc\n\n## Problem\n\n" + "\n\n".join(f"Paragraph {i}." for i in range(80))
    (tmp_path / "req-001.md").write_text(body + "\n\n## Requirements\n\n[REQ-001] x.\n")
    app = ExplorerApp(str(tmp_path))
    async with app.run_test(size=(100, 24)) as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"open req-001")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        pane = app.screen.query_one("#content-scroll", VerticalScroll)
        assert app.focused is pane  # the document is under the keyboard
        await pilot.press("j", "j")
        await pilot.pause()
        assert pane.scroll_offset.y > 0
        await pilot.press("k")
        await pilot.pause()

        # Re-opening resets the reading position to the top.
        scrolled = pane.scroll_offset.y
        assert scrolled > 0
        app.screen.open_artifact(str(tmp_path / "req-001.md"))
        await pilot.pause()
        assert pane.scroll_offset.y == 0


@pytest.mark.asyncio
async def test_markdown_links_navigate_in_app(tmp_path):
    (tmp_path / "adr-001.md").write_text(
        "# ADR-001 Choose\n\n## Status\n\nAccepted\n\n## Context\n\nc\n\n## Decision\n\nd\n"
    )
    (tmp_path / "req-001.md").write_text(
        "# Search Feature\n\n## Problem\n\nSee [the decision](adr-001.md).\n\n"
        "## Requirements\n\n[REQ-001] x.\n"
    )
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"open req-001")
        await pilot.press("enter")
        await pilot.pause()

        # Activate the in-document reference (pointer event, posted directly).
        markdown = app.screen.query_one("#artifact-markdown", Markdown)
        view = app.screen.query_one(ContextView)
        view.post_message(Markdown.LinkClicked(markdown, "adr-001.md"))
        await pilot.pause()
        await pilot.pause()
        title = str(app.screen.query_one("#context-region").border_title)
        assert "adr-001" in title  # walked the hypertext

        await pilot.press("escape")  # the same history walks back
        await pilot.pause()
        title = str(app.screen.query_one("#context-region").border_title)
        assert "req-001" in title

        # An unresolvable link reports and stays put.
        view.post_message(Markdown.LinkClicked(markdown, "missing.md"))
        await pilot.pause()
        assert "req-001" in str(app.screen.query_one("#context-region").border_title)


@pytest.mark.asyncio
async def test_tabs_carry_count_badges():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"open adr-001")
        await pilot.press("enter")
        await pilot.pause()
        tabs = app.screen.query_one(TabbedContent)
        assert str(tabs.get_tab("tab-links").label) == "Links (1)"
        assert str(tabs.get_tab("tab-findings").label) == "Findings"  # none — no badge


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
        # The knowledge-graph grammar: a Relationships chain, an Impact
        # Analysis block, and a Lineage section (DESIGN-knowledge-graph).
        assert "Relationships" in panel and "Lineage" in panel
        assert "Impact Analysis" in panel
        assert "Changing:" in panel and "May affect:" in panel

        await pilot.press("enter")  # open the first connected artifact
        await pilot.pause()
        title = str(app.screen.query_one("#context-region").border_title)
        assert "req-001" in title  # traversed across the graph

        await pilot.press("escape")  # back through view history
        await pilot.pause()
        title = str(app.screen.query_one("#context-region").border_title)
        assert "adr-001" in title


def test_render_sections_uses_knowledge_graph_grammar():
    # DESIGN-knowledge-graph: dependency chain, Impact Analysis block, lineage
    # chain — a pure render over RelationshipsView, no fixtures needed.
    from rac.explorer.state import RelationshipLink, RelationshipsView
    from rac.explorer.widgets.views import render_sections

    view = RelationshipsView(
        id="REQ-004",
        title="Payment Retry",
        path="rac/requirements/req-004.md",
        outgoing=(RelationshipLink("Related Decisions", "ADR-012 (Provider)", "p.md", True),),
        impact=(RelationshipLink("Superseded By", "PROMPT-007", "q.md", True),),
        lineage=("Supersedes → ADR-001", "Superseded By ← ADR-020"),
    )
    out = render_sections(view)

    # Relationships render as a chain whose ↓ carries the edge kind.
    assert "REQ-004" in out
    assert "↓ Related Decisions" in out
    assert "ADR-012 (Provider)" in out
    # Impact Analysis frames the change.
    assert "Impact Analysis" in out
    assert "Changing:" in out and "May affect:" in out
    assert "PROMPT-007 (Superseded By)" in out
    # Lineage steps join into a vertical chain (one ↓ between two steps).
    lineage = out.split("Lineage", 1)[1]
    assert lineage.count("↓") == 1
    assert "Supersedes → ADR-001" in lineage and "Superseded By ← ADR-020" in lineage

    # Empty sections keep plain-language fallbacks.
    bare = render_sections(
        RelationshipsView(id="X", title=None, path="x.md", outgoing=(), impact=(), lineage=())
    )
    assert "none declared" in bare
    assert "nothing depends on this artifact" in bare
    assert "no recorded supersession" in bare


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
async def test_context_e_terminal_editor_needs_suspend(monkeypatch):
    # Headless sessions cannot suspend; the terminal-editor path must fall
    # back to guidance instead of crashing or launching blind.
    import rac.explorer.editor as editor_mod

    launched: list[list[str]] = []
    monkeypatch.setattr(editor_mod, "_BLOCKING_RUNNER", lambda cmd: launched.append(list(cmd)))
    monkeypatch.setenv("EDITOR", "vim")
    monkeypatch.delenv("VISUAL", raising=False)

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        await pilot.press("e")
        await pilot.pause()
        status = str(app.screen.query_one("#context-status", Static).content)
        assert "vim" in status and "suspend" in status
        assert launched == []  # nothing ran without a terminal to hand over


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
        assert isinstance(app.focused, Input)
        await pilot.press(*"open adr-001")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-context"
        text = str(app.screen.query_one("#context-panel", Static).content)
        assert "decision" in text


@pytest.mark.asyncio
async def test_search_all_renders_results_in_context_region():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        screen = app.screen
        await pilot.press("/")
        await pilot.press(*"search feature")
        await pilot.pause()
        # The last menu row hands the text to full search routing.
        menu = screen.query_one("#palette-menu", OptionList)
        menu.highlighted = menu.option_count - 1
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
        assert results.option_count == len(commands.REGISTRY)  # the whole registry, nothing more


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
async def test_slash_browse_with_type_lists_in_results_view():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"browse decision")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-results"
        region = app.screen.query_one("#context-region")
        assert str(region.border_title) == "Results · 1"
        await pilot.press("enter")  # first (highlighted) result opens
        await pilot.pause()
        assert app.screen.current_view == "view-context"
        context = app.screen.query_one(ContextView).context
        assert context is not None and context.type == "decision"


@pytest.mark.asyncio
async def test_slash_browse_behaves_the_same_in_type_grouping():
    from rac.explorer.preferences import Preferences, save_preferences

    save_preferences(Preferences(artifact_grouping="type"))
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"browse decision")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-results"  # not a sidebar group

        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("/")
        await pilot.press(*"browse nonsense")
        await pilot.press("enter")
        await pilot.pause()
        results = app.screen.query_one("#command-results", OptionList)
        listing = "\n".join(
            str(results.get_option_at_index(i).prompt) for i in range(results.option_count)
        )
        assert "Nothing to browse: nonsense" in listing


@pytest.mark.asyncio
async def test_bare_slash_browse_focuses_the_sidebar():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"browse")
        await pilot.press("enter")
        await pilot.pause()
        assert app.focused is app.screen.query_one(NavigationSidebar)


# --- settings ---------------------------------------------------------------------


async def _open_settings(app: ExplorerApp, pilot, command: str = "settings") -> None:
    await pilot.press("/")
    await pilot.press(*command)
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_slash_settings_opens_interactive_view():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_settings(app, pilot)
        assert app.screen.current_view == "view-settings"
        listing = app.screen.query_one("#settings-list", OptionList)
        keys = [listing.get_option_at_index(i).id for i in range(listing.option_count)]
        assert keys == [
            "theme",
            "mascot",
            "animations",
            "mascot_interaction",
            "artifact_grouping",
            "editor",
        ]
        footer = str(app.screen.query_one("#settings-footer", Static).content)
        assert "explorer.json" in footer


@pytest.mark.asyncio
async def test_preferences_command_still_opens_settings():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_settings(app, pilot, command="preferences")
        assert app.screen.current_view == "view-settings"


@pytest.mark.asyncio
async def test_settings_theme_cycles_live_and_persists():
    from rac.explorer.preferences import load_preferences

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_settings(app, pilot)
        assert app.theme == "rac-lantern"
        await pilot.press("enter")  # theme row (highlighted first)
        await pilot.pause()
        assert app.theme != "rac-lantern"  # applied live
        assert load_preferences().theme == app.theme  # and persisted


@pytest.mark.asyncio
async def test_settings_toggle_persists_across_sessions():
    from rac.explorer.preferences import load_preferences

    directory = str(FIXTURES / "valid_clean")
    app = ExplorerApp(directory)
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_settings(app, pilot)
        await pilot.press("down", "enter")  # mascot row → toggle off
        await pilot.pause()
        assert load_preferences().mascot is False

    app2 = ExplorerApp(directory)
    assert app2.adapter.preferences.mascot is False  # next session adopts it


@pytest.mark.asyncio
async def test_settings_editor_row_takes_typed_input():
    from rac.explorer.preferences import load_preferences

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_settings(app, pilot)
        await pilot.press("down", "down", "down", "down", "down", "enter")  # editor row
        await pilot.pause()
        field = app.screen.query_one("#settings-editor-input", Input)
        assert field.display and app.focused is field

        await pilot.press(*"code --wait")
        await pilot.press("enter")
        await pilot.pause()
        assert load_preferences().editor == "code --wait"
        assert not field.display  # back to the list, row shows the value
        listing = app.screen.query_one("#settings-list", OptionList)
        rendered = " ".join(
            str(listing.get_option_at_index(i).prompt) for i in range(listing.option_count)
        )
        assert "code --wait" in rendered


@pytest.mark.asyncio
async def test_settings_grouping_cycles_three_values_and_rebuilds_sidebar():
    from rac.explorer.preferences import load_preferences

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_settings(app, pilot)
        sidebar = app.screen.query_one(NavigationSidebar)

        await pilot.press("down", "down", "down", "down", "enter")  # folders → type
        await pilot.pause()
        assert load_preferences().artifact_grouping == "type"
        assert all((node.data or "").startswith("group:") for node in sidebar.root.children)

        await pilot.press("enter")  # type → flat
        await pilot.pause()
        assert load_preferences().artifact_grouping == "flat"
        assert all((node.data or "").endswith(".md") for node in sidebar.root.children)

        await pilot.press("enter")  # flat → folders (the default)
        await pilot.pause()
        assert load_preferences().artifact_grouping == "folders"


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
        # The optional editor step (v0.8.11): one prefilled, skippable line.
        text = str(app.screen.query_one(RepositoryPanel).content)
        assert "Choose your editor" in text
        assert firstrun.is_first_run()  # not onboarded until the step ends

        await pilot.press("enter")  # accept: empty keeps the env fallback
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

        await pilot.press("enter")  # welcome → editor step
        await pilot.press("enter")  # accept the editor default
        await pilot.pause()
        text = str(app.screen.query_one(RepositoryPanel).content)
        assert "Health" in text


@pytest.mark.asyncio
async def test_first_run_welcome_shows_mascot_when_enabled(fresh_first_run):
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        art = app.screen.query_one("#mascot", Static)
        assert art.display  # mascot present by default
        assert mascot.label(mascot.DISCOVERY) in str(art.content)


@pytest.mark.asyncio
async def test_mascot_can_be_disabled(fresh_first_run, tmp_path, monkeypatch):
    from rac.explorer.preferences import Preferences, save_preferences

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    save_preferences(Preferences(mascot=False))
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert not app.screen.query_one("#mascot", Static).display  # art gone
        assert "Repository found" in text  # but no information is lost


def test_mascot_frames_are_equal_sized_per_state():
    # DESIGN-mascot-animations: cycling frames must never shift the layout.
    for state in (mascot.IDLE, mascot.SEARCHING, mascot.DISCOVERY, mascot.EMPTY):
        sequence = mascot.frames(state)
        assert len(sequence) >= 1
        shapes = {
            (len(frame.split("\n")), max(len(line) for line in frame.split("\n")))
            for frame in sequence
        }
        assert len(shapes) == 1  # one height and one width per state
    # Every frame still carries the text label (ADR-028).
    assert mascot.label(mascot.SEARCHING) in mascot.figure(mascot.SEARCHING, 2)


@pytest.mark.asyncio
async def test_mascot_animates_only_with_animations_on(fresh_first_run):
    from rac.explorer.widgets.views import HomeView

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        home = app.screen.query_one(HomeView)
        art = app.screen.query_one("#mascot", Static)

        # Animations on: cycling the frames moves the lantern. Sample across
        # full cycles rather than asserting a single tick — a background timer
        # also advances the frame and some sequences repeat one (the DISCOVERY
        # pulse is ✶ ✦ ✶), so a lone tick can land on an identical frame.
        home.show_mascot(mascot.SEARCHING)
        await pilot.pause()
        seen = set()
        for _ in range(len(mascot.frames(mascot.SEARCHING)) * 2):
            seen.add(str(art.content))
            home._tick_mascot()
            await pilot.pause()
        assert len(seen) > 1  # the lantern moved through distinct frames

        # With animations off the figure holds its first frame.
        from dataclasses import replace

        app.adapter.preferences = replace(app.adapter.preferences, animations=False)
        home.show_mascot(mascot.DISCOVERY)
        held = str(art.content)
        home._tick_mascot()
        await pilot.pause()
        assert str(art.content) == held


@pytest.mark.asyncio
async def test_mascot_searches_while_loading(fresh_first_run):
    from rac.explorer.state import LoadProgressState
    from rac.explorer.widgets.views import HomeView

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        home = app.screen.query_one(HomeView)
        home.show_progress(
            LoadProgressState(phase="scan", completed=0, total=None, label="Scanning artifacts")
        )
        art = app.screen.query_one("#mascot", Static)
        assert mascot.label(mascot.SEARCHING) in str(art.content)


def test_mascot_interaction_message_is_deterministic():
    # DESIGN-mascot-interaction: a pure, testable mapping from selection count
    # to response — acknowledgement first, rare line at exactly RARE_AT,
    # guidance on a cadence, discovery messages rotating otherwise.
    assert mascot.interaction_message(1) == mascot.ACK
    assert mascot.interaction_message(0) == mascot.ACK  # never negative-indexes
    assert mascot.interaction_message(2) == mascot.DISCOVERY_MESSAGES[0]
    assert mascot.interaction_message(3) == mascot.DISCOVERY_MESSAGES[1]
    assert mascot.interaction_message(4) == mascot.GUIDANCE
    assert mascot.interaction_message(mascot.RARE_AT) == mascot.RARE
    # The rare line wins even though its position is otherwise a discovery slot.
    assert mascot.RARE not in {mascot.interaction_message(n) for n in range(1, mascot.RARE_AT)}
    # Deterministic and total over a wide range; every response is real text.
    for count in range(0, 60):
        first = mascot.interaction_message(count)
        assert first == mascot.interaction_message(count)
        assert first.strip()


@pytest.mark.asyncio
async def test_mascot_selection_appends_response(fresh_first_run):
    from rac.explorer.widgets.views import MascotArt

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        art = app.screen.query_one("#mascot", MascotArt)
        assert art.can_focus  # selectable by default (DESIGN-mascot-interaction)
        figure_only = str(art.content)
        assert mascot.ACK not in figure_only  # no response until selected

        art.focus()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert mascot.ACK in str(art.content)  # inline, no popup

        # Repeated selection rotates through discovery and reaches the rare line.
        for _ in range(mascot.RARE_AT - 1):
            await pilot.press("enter")
            await pilot.pause()
        assert mascot.RARE in str(art.content)


@pytest.mark.asyncio
async def test_mascot_click_selects(fresh_first_run):
    from rac.explorer.widgets.views import MascotArt

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.click("#mascot")
        await pilot.pause()
        art = app.screen.query_one("#mascot", MascotArt)
        assert mascot.ACK in str(art.content)


@pytest.mark.asyncio
async def test_mascot_interaction_can_be_disabled(fresh_first_run, tmp_path, monkeypatch):
    from rac.explorer.preferences import Preferences, save_preferences
    from rac.explorer.widgets.views import MascotArt

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    save_preferences(Preferences(mascot_interaction=False))
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        art = app.screen.query_one("#mascot", MascotArt)
        assert art.display  # mascot still present (its own toggle is on)
        assert not art.can_focus  # but inert
        art.activate()  # selecting it does nothing
        assert mascot.ACK not in str(art.content)
        assert "Repository found" in text  # and the Explorer is unaffected


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
        assert "Artifacts      1200" in text
        # Folders default builds eagerly: 1200 root-level leaves at once.
        sidebar = app.screen.query_one(NavigationSidebar)
        assert len(sidebar.root.children) == 1200
    assert time.monotonic() - started < 60  # generous ceiling; catch regressions


@pytest.mark.asyncio
async def test_quit_binding_exits_cleanly():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("q")
    assert not app.is_running


# --- v0.8.8 refinements --------------------------------------------------------------


@pytest.mark.asyncio
async def test_esc_never_dead_ends():
    # A context view reached via resume has no history — Esc still goes home.
    directory = str(FIXTURES / "valid_clean")
    app = ExplorerApp(directory)
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        await pilot.press("q")

    app2 = ExplorerApp(directory)
    async with app2.run_test() as pilot:
        await _settled_panel_text(app2, pilot)
        await pilot.press("full_stop")  # resume straight into the artifact
        await pilot.pause()
        assert app2.screen.current_view == "view-context"
        await pilot.press("escape")
        await pilot.pause()
        assert app2.screen.current_view == "view-home"


@pytest.mark.asyncio
async def test_resume_restores_the_last_view():
    directory = str(FIXTURES / "valid_clean")
    app = ExplorerApp(directory)
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")  # leave the session on the health view
        await pilot.pause()
        assert app.screen.current_view == "view-health"
        await pilot.press("q")

    app2 = ExplorerApp(directory)
    async with app2.run_test() as pilot:
        await _settled_panel_text(app2, pilot)
        await pilot.press("full_stop")
        await pilot.pause()
        assert app2.screen.current_view == "view-health"  # the view, not just the artifact


@pytest.mark.asyncio
async def test_question_mark_opens_help():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("question_mark")
        await pilot.pause()
        assert app.screen.current_view == "view-results"
        results = app.screen.query_one("#command-results", OptionList)
        assert results.option_count == len(commands.REGISTRY)  # the whole registry


@pytest.mark.asyncio
async def test_results_title_carries_the_count_and_empty_uses_mascot():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        screen = app.screen
        screen.route_command("find feature")
        await pilot.pause()
        title = str(screen.query_one("#context-region").border_title)
        assert title.startswith("Results · ")

        screen.route_command("find zzz-no-such-thing")
        await pilot.pause()
        assert str(screen.query_one("#context-region").border_title) == "Results · 0"
        results = screen.query_one("#command-results", OptionList)
        rendered = " ".join(
            str(results.get_option_at_index(i).prompt) for i in range(results.option_count)
        )
        assert mascot.label(mascot.EMPTY) in rendered  # a calm empty state


@pytest.mark.asyncio
async def test_sidebar_e_opens_highlighted_artifact_in_editor(monkeypatch):
    import rac.explorer.editor as editor_mod

    launched: list[list[str]] = []
    monkeypatch.setattr(editor_mod, "_RUNNER", lambda cmd: launched.append(list(cmd)))
    monkeypatch.setenv("EDITOR", "code")

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")  # sidebar
        await pilot.press("down", "enter")  # expand first group
        await pilot.pause()
        await pilot.press("down")  # highlight the first artifact
        await pilot.press("e")
        await pilot.pause()
        assert launched and launched[0][0] == "code"
        assert launched[0][-1].endswith(".md")


@pytest.mark.asyncio
async def test_app_bar_shows_short_version_and_tilde_path(tmp_path, monkeypatch):
    from rac.explorer.widgets.appbar import _SHORT_VERSION, _tilde

    assert "+" not in _SHORT_VERSION  # local-build suffix trimmed
    monkeypatch.setenv("HOME", str(tmp_path))
    inside = tmp_path / "work" / "repo"
    assert _tilde(str(inside)) == "~/work/repo"
    assert _tilde("rac/") == "rac/"  # non-home paths stay as they are


# --- live reload (v0.8.9) -------------------------------------------------------


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    import shutil

    target = tmp_path / name
    shutil.copytree(FIXTURES / name, target)
    return target


async def _force_scan(app: ExplorerApp, pilot) -> None:
    """One watcher cycle, deterministically (the 2s interval is too slow here)."""
    screen = app.screen
    assert isinstance(screen, MainScreen)
    screen.resume_watching()
    await app.workers.wait_for_complete()  # the scan
    await pilot.pause()
    await app.workers.wait_for_complete()  # the reload it may have triggered
    await pilot.pause()


@pytest.mark.asyncio
async def test_watcher_reloads_when_an_artifact_changes_on_disk(tmp_path):
    repo = _copy_fixture("valid_clean", tmp_path)
    app = ExplorerApp(str(repo))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        (repo / "note.md").write_text("# A New Note\n", encoding="utf-8")
        text = str(app.screen.query_one(RepositoryPanel).content)
        assert "Artifacts      2" in text  # not yet seen
        await _force_scan(app, pilot)
        text = str(app.screen.query_one(RepositoryPanel).content)
        assert "Artifacts      3" in text


@pytest.mark.asyncio
async def test_watcher_refreshes_the_open_artifact_in_place(tmp_path):
    repo = _copy_fixture("valid_clean", tmp_path)
    app = ExplorerApp(str(repo))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        view = app.screen.query_one(ContextView)
        assert view.context is not None
        path = Path(view.context.path)
        original = path.read_text(encoding="utf-8")

        path.write_text(original + "\nA fresh paragraph saved outside.\n", encoding="utf-8")
        await _force_scan(app, pilot)

        assert app.screen.current_view == "view-context"
        assert view.context is not None and view.context.path == str(path)
        document = app.screen.query_one("#artifact-markdown", Markdown)
        assert "A fresh paragraph saved outside." in document.source


@pytest.mark.asyncio
async def test_watcher_falls_back_home_when_the_open_artifact_disappears(tmp_path):
    repo = _copy_fixture("valid_clean", tmp_path)
    app = ExplorerApp(str(repo))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        view = app.screen.query_one(ContextView)
        assert view.context is not None
        Path(view.context.path).unlink()

        await _force_scan(app, pilot)
        assert app.screen.current_view == "view-home"


@pytest.mark.asyncio
async def test_watcher_is_quiet_while_paused_and_before_first_load(tmp_path):
    repo = _copy_fixture("valid_clean", tmp_path)
    app = ExplorerApp(str(repo))
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, MainScreen)
        await _settled_panel_text(app, pilot)

        screen.pause_watching()
        (repo / "note.md").write_text("# A New Note\n", encoding="utf-8")
        screen._watch_tick()
        await app.workers.wait_for_complete()
        await pilot.pause()
        text = str(screen.query_one(RepositoryPanel).content)
        assert "Artifacts      2" in text  # paused: the change was not picked up

        await _force_scan(app, pilot)  # resume scans immediately
        text = str(screen.query_one(RepositoryPanel).content)
        assert "Artifacts      3" in text


@pytest.mark.asyncio
async def test_watcher_does_not_run_after_a_load_error(tmp_path, monkeypatch):
    # A genuine load failure (WS4: not a malformed artifact, which now degrades
    # gracefully) leaves the watcher with no baseline; a file change does not
    # auto-recover — only `r` does.
    import rac.explorer.adapter as adapter_mod

    def _boom(*args, **kwargs):
        raise RuntimeError("core exploded")

    monkeypatch.setattr(adapter_mod, "load_repository", _boom)
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, MainScreen)
        await _settled_panel_text(app, pilot)
        assert screen._watch_baseline is None  # load failed: nothing to compare

        (tmp_path / "note.md").write_text("# Repaired Note\n", encoding="utf-8")
        screen._watch_tick()
        await app.workers.wait_for_complete()
        await pilot.pause()
        text = str(screen.query_one(RepositoryPanel).content)
        assert "Could not load repository" in text  # only `r` recovers


# --- validation drill-down (v0.8.9) ---------------------------------------------


@pytest.mark.asyncio
async def test_attention_item_lands_on_the_inspection_tab():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")
        await pilot.pause()
        await pilot.press("enter")  # first attention item (highlighted)
        await pilot.pause()
        assert app.screen.current_view == "view-context"
        tabs = app.screen.query_one(TabbedContent)
        assert tabs.active == "tab-inspection"
        panel = str(app.screen.query_one("#context-panel", Static).content)
        assert "Diagnostics" in panel
        assert "✓ none" not in panel  # the reason is on the tab, not a dead end


@pytest.mark.asyncio
async def test_recommendation_lands_on_the_findings_tab():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"recommendations")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")  # first recommendation (highlighted)
        await pilot.pause()
        assert app.screen.current_view == "view-context"
        assert app.screen.query_one(TabbedContent).active == "tab-findings"
        panel = str(app.screen.query_one("#findings-panel", Static).content)
        assert "✓ No findings" not in panel


@pytest.mark.asyncio
async def test_inspection_tab_carries_a_diagnostics_badge():
    app = ExplorerApp(str(FIXTURES / "invalid_known"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        tabs = app.screen.query_one(TabbedContent)
        label = str(tabs.get_tab("tab-inspection").label)
        assert label.startswith("Inspection (") and label != "Inspection (0)"


# --- improvement suggestions on findings (v0.8.9) --------------------------------


@pytest.mark.asyncio
async def test_findings_tab_carries_improvement_suggestions(tmp_path):
    (tmp_path / "req-sparse.md").write_text(
        "# Sparse Feature\n\n## Problem\n\nUsers cannot do the thing.\n\n"
        "## Requirements\n\n[REQ-001] Users can do the thing.\n",
        encoding="utf-8",
    )
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        panel = str(app.screen.query_one("#findings-panel", Static).content)
        assert "Improvement" in panel
        assert "Missing recommended section: Success Metrics" in panel
        # The badge counts review findings and improvements together.
        label = str(app.screen.query_one(TabbedContent).get_tab("tab-findings").label)
        assert label.startswith("Findings (")


# --- command surface depth (v0.8.9) -----------------------------------------------


@pytest.mark.asyncio
async def test_schema_command_lists_types_and_renders_detail():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"schema")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-results"
        results = app.screen.query_one("#command-results", OptionList)
        listing = "\n".join(
            str(results.get_option_at_index(i).prompt) for i in range(results.option_count)
        )
        assert "decision" in listing and "requirement" in listing

        await pilot.press("/")
        await pilot.press(*"schema decision")
        await pilot.press("enter")
        await pilot.pause()
        results = app.screen.query_one("#command-results", OptionList)
        detail = str(results.get_option_at_index(0).prompt)
        assert "Required sections" in detail
        assert "Status" in detail


@pytest.mark.asyncio
async def test_schema_command_reports_unknown_types():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"schema nonsense")
        await pilot.press("enter")
        await pilot.pause()
        results = app.screen.query_one("#command-results", OptionList)
        listing = "\n".join(
            str(results.get_option_at_index(i).prompt) for i in range(results.option_count)
        )
        assert "Unknown artifact type: nonsense" in listing


@pytest.mark.asyncio
async def test_palette_offers_recent_artifacts_before_typing():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _open_first_artifact(app, pilot)
        await pilot.press("escape")  # back home so the palette opens fresh
        await pilot.pause()

        await pilot.press("/")
        palette = app.screen.query_one(CommandPalette)
        menu = palette.query_one("#palette-menu", OptionList)
        labels = [str(menu.get_option_at_index(i).prompt) for i in range(menu.option_count)]
        assert any("Recent" in label for label in labels)
        # More rows than the registry alone: recents plus their headers.
        assert menu.option_count > len(commands.REGISTRY)
        # The first selectable row is the most recent artifact — Enter reopens it.
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-context"


@pytest.mark.asyncio
async def test_results_filter_cycles_types_with_f():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))  # one requirement, one decision
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"find 001")  # matches both artifacts
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-results"
        results = app.screen.query_one("#command-results", OptionList)
        assert results.option_count == 2
        filter_line = app.screen.query_one("#results-filter", Static)
        assert filter_line.display
        assert "Filter: all · 2 of 2" in str(filter_line.content)

        await pilot.press("f")  # all → first type present
        await pilot.pause()
        assert results.option_count == 1
        assert "1 of 2" in str(filter_line.content)

        await pilot.press("f", "f")  # second type → back to all
        await pilot.pause()
        assert results.option_count == 2
        assert "Filter: all" in str(filter_line.content)


# --- the directory view (folders grouping, v0.8.10) -------------------------------


def _nested_repo(tmp_path: Path) -> Path:
    (tmp_path / "roadmaps" / "v1").mkdir(parents=True)
    (tmp_path / "decisions").mkdir()
    (tmp_path / "roadmaps" / "v1" / "deep-roadmap.md").write_text(
        "# Deep Roadmap\n\n## Outcomes\n\nShip.\n\n## Initiatives\n\nBuild.\n\n"
        "## Success Measures\n\nShipped.\n",
        encoding="utf-8",
    )
    (tmp_path / "decisions" / "some-call.md").write_text("# Some Call\n", encoding="utf-8")
    (tmp_path / "top-note.md").write_text("# Top Note\n", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_sidebar_mirrors_the_directory_structure_by_default(tmp_path):
    app = ExplorerApp(str(_nested_repo(tmp_path)))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        sidebar = app.screen.query_one(NavigationSidebar)
        labels = [str(node.label) for node in sidebar.root.children]
        # Directories first (trailing slash + dim count), then root leaves.
        assert labels[0].startswith("decisions/") and "1" in labels[0]
        assert labels[1].startswith("roadmaps/") and "1" in labels[1]
        assert "Top Note" in labels[2]

        roadmaps = sidebar.root.children[1]
        assert roadmaps.data == "dir:roadmaps"
        v1 = roadmaps.children[0]
        assert v1.data == "dir:roadmaps/v1"
        leaf_label = str(v1.children[0].label)
        assert leaf_label.startswith("RMP ") and "Deep Roadmap" in leaf_label


@pytest.mark.asyncio
async def test_folder_expansion_and_cursor_survive_reload(tmp_path):
    app = ExplorerApp(str(_nested_repo(tmp_path)))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")  # sidebar
        await pilot.press("down", "down", "enter")  # roadmaps/ → expand
        await pilot.pause()
        await pilot.press("down", "enter")  # v1/ → expand
        await pilot.pause()
        await pilot.press("down")  # cursor on the nested artifact leaf
        await pilot.pause()
        sidebar = app.screen.query_one(NavigationSidebar)
        cursor_data = sidebar.cursor_node.data
        assert cursor_data is not None and cursor_data.endswith("deep-roadmap.md")

        await pilot.press("r")  # manual reload
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.pause()
        roadmaps = sidebar.root.children[1]
        assert roadmaps.is_expanded and roadmaps.children[0].is_expanded
        assert sidebar.cursor_node is not None
        assert sidebar.cursor_node.data == cursor_data

        # The watcher's reload keeps the place too (v0.8.9 continuity).
        (tmp_path / "another.md").write_text("# Another\n", encoding="utf-8")
        await _force_scan(app, pilot)
        roadmaps = sidebar.root.children[1]
        assert roadmaps.is_expanded and roadmaps.children[0].is_expanded


@pytest.mark.asyncio
async def test_open_reveals_a_nested_artifact_along_its_path(tmp_path):
    app = ExplorerApp(str(_nested_repo(tmp_path)))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"open deep-roadmap")
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.current_view == "view-context"
        sidebar = app.screen.query_one(NavigationSidebar)
        roadmaps = sidebar.root.children[1]
        assert roadmaps.is_expanded  # the ancestor chain opened
        assert roadmaps.children[0].is_expanded
        assert sidebar.cursor_node is not None
        assert (sidebar.cursor_node.data or "").endswith("deep-roadmap.md")


@pytest.mark.asyncio
async def test_directory_rows_neither_open_nor_edit(tmp_path):
    app = ExplorerApp(str(_nested_repo(tmp_path)))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")  # sidebar
        await pilot.press("down", "enter")  # decisions/ — expands, must not open
        await pilot.pause()
        assert app.screen.current_view == "view-home"
        await pilot.press("e")  # a directory row has no file to edit
        await pilot.pause()
        assert app.screen.current_view == "view-home"


# --- artifact creation and portfolio stats (v0.8.10) ------------------------------


async def _route(app: ExplorerApp, pilot, command: str) -> None:
    await pilot.press("/")
    await pilot.press(*command)
    await pilot.press("enter")
    await pilot.pause()


@pytest.mark.asyncio
async def test_bare_new_lists_creatable_types_and_usage():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _route(app, pilot, "new")
        assert app.screen.current_view == "view-results"
        results = app.screen.query_one("#command-results", OptionList)
        listing = "\n".join(
            str(results.get_option_at_index(i).prompt) for i in range(results.option_count)
        )
        for name in ("requirement", "decision", "roadmap", "prompt", "design"):
            assert name in listing
        assert "Usage: /new <type> <path>" in listing


@pytest.mark.asyncio
async def test_new_previews_then_confirm_creates_and_opens(tmp_path):
    from rac.services.init import init_repository

    init_repository(str(tmp_path), key="RAC")
    (tmp_path / "seed.md").write_text("# Seed Note\n", encoding="utf-8")
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        target = tmp_path / "adr-demo.md"
        await _route(app, pilot, f"new decision {target}")
        assert app.screen.current_view == "view-import"
        panel = str(app.screen.query_one("#import-panel", Static).content)
        assert "ID assigned on write" in panel
        assert not target.exists()  # nothing written before the confirm

        await pilot.press("y")
        await app.workers.wait_for_complete()  # the reload the write triggers
        await pilot.pause()
        await pilot.pause()
        assert target.exists()
        text = target.read_text(encoding="utf-8")
        assert text.startswith("---\n") and "id: RAC-" in text

        # The new artifact opened, and the sidebar knows it.
        assert app.screen.current_view == "view-context"
        view = app.screen.query_one(ContextView)
        assert view.context is not None and view.context.path == str(target)
        sidebar = app.screen.query_one(NavigationSidebar)
        assert str(target) in sidebar._node_by_data


@pytest.mark.asyncio
async def test_new_onto_an_existing_file_refuses_and_writes_nothing(tmp_path):
    from rac.services.init import init_repository

    init_repository(str(tmp_path), key="RAC")
    taken = tmp_path / "taken.md"
    taken.write_text("# Mine\n", encoding="utf-8")
    app = ExplorerApp(str(tmp_path))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _route(app, pilot, f"new decision {taken}")
        await pilot.press("y")
        await app.workers.wait_for_complete()
        await pilot.pause()
        panel = str(app.screen.query_one("#import-panel", Static).content)
        assert "Refusing to overwrite" in panel
        assert taken.read_text(encoding="utf-8") == "# Mine\n"
        assert app.screen.current_view == "view-import"  # no reload, no open


@pytest.mark.asyncio
async def test_stats_command_renders_the_dashboard():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await _route(app, pilot, "stats")
        assert app.screen.current_view == "view-stats"
        await app.workers.wait_for_complete()  # the collection worker
        await pilot.pause()
        panel = str(app.screen.query_one("#stats-panel", Static).content)
        assert "Portfolio Statistics" in panel
        assert "Overview" in panel and "Requirements & Quality" in panel
        assert "Decisions" in panel

        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.current_view == "view-home"


# --- first-run editor prompt (v0.8.11) --------------------------------------------


@pytest.mark.asyncio
async def test_first_run_editor_prompt_persists_a_typed_command(fresh_first_run):
    from rac.explorer.preferences import load_preferences

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")  # welcome → editor step
        await pilot.pause()
        assert app.focused is app.screen.query_one("#firstrun-editor", Input)

        await pilot.press(*"code --wait")
        await pilot.press("enter")
        await pilot.pause()
        assert load_preferences().editor == "code --wait"
        assert not firstrun.is_first_run()
        text = str(app.screen.query_one(RepositoryPanel).content)
        assert "Health" in text  # onboarding finished into the summary


@pytest.mark.asyncio
async def test_first_run_editor_prompt_empty_enter_keeps_the_fallback(fresh_first_run):
    from rac.explorer.preferences import load_preferences

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter", "enter")  # welcome → step → accept empty
        await pilot.pause()
        assert load_preferences().editor == ""  # the $VISUAL/$EDITOR fallback
        assert not firstrun.is_first_run()


@pytest.mark.asyncio
async def test_first_run_editor_prompt_esc_skips_without_writing(fresh_first_run, monkeypatch):
    from rac.explorer.preferences import preferences_path

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")  # welcome → editor step
        await pilot.press("escape")  # skip
        await pilot.pause()
        assert not preferences_path().exists()  # nothing written
        assert not firstrun.is_first_run()  # but onboarding completed
        text = str(app.screen.query_one(RepositoryPanel).content)
        assert "Health" in text
        assert not app.screen.query_one("#firstrun-editor", Input).display


@pytest.mark.asyncio
async def test_returning_users_never_see_the_editor_prompt():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Choose your editor" not in text
        assert not app.screen.query_one("#firstrun-editor", Input).display
