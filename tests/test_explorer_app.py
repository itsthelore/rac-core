"""Headless screen tests for the Explorer shell (v0.8.0, ADR-027).

Runs the Textual app through ``App.run_test()`` (no real terminal). Worker
results are awaited via ``app.workers.wait_for_complete()`` before asserting,
keeping the thread-worker tests deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rac.explorer import firstrun
from rac.explorer.app import ExplorerApp
from rac.explorer.widgets import RepositoryPanel

FIXTURES = Path(__file__).parent / "fixtures" / "portfolio_summary"


@pytest.fixture(autouse=True)
def onboarded_state(tmp_path_factory, monkeypatch):
    """Run every app test as a returning user; onboarding tests reset this."""
    state = tmp_path_factory.mktemp("xdg-state")
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    firstrun.mark_onboarded()
    return state


@pytest.fixture
def fresh_first_run(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "fresh-state"))


async def _settled_panel_text(app: ExplorerApp, pilot) -> str:
    await app.workers.wait_for_complete()
    await pilot.pause()
    return str(app.screen.query_one(RepositoryPanel).content)


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
async def test_browse_open_context_and_esc_stack():
    from rac.explorer.screens.browser import BrowserScreen
    from rac.explorer.screens.context import ContextScreen
    from rac.explorer.screens.repository import RepositoryScreen

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)

        await pilot.press("enter")  # home → browser
        assert isinstance(app.screen, BrowserScreen)

        await pilot.press("enter")  # first artifact → context view
        assert isinstance(app.screen, ContextScreen)
        from textual.widgets import Static

        text = str(app.screen.query_one("#context-panel", Static).content)
        assert "ID " in text and "Status " in text
        assert "Completeness  ✓ all recommended sections present" in text
        assert "Relationships" in text and "Diagnostics" in text

        await pilot.press("escape")  # context → browser
        assert isinstance(app.screen, BrowserScreen)
        await pilot.press("escape")  # browser → home
        assert isinstance(app.screen, RepositoryScreen)


@pytest.mark.asyncio
async def test_home_shows_attention_and_hint():
    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        text = await _settled_panel_text(app, pilot)
        assert "Attention" in text
        assert "! 1 broken relationship" in text
        assert "Press / for anything" in text


@pytest.mark.asyncio
async def test_slash_open_navigates_to_context():
    from rac.explorer.screens.command import CommandScreen
    from rac.explorer.screens.context import ContextScreen

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        assert isinstance(app.screen, CommandScreen)
        await pilot.press(*"open adr-001")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ContextScreen)
        from textual.widgets import Static

        text = str(app.screen.query_one("#context-panel", Static).content)
        assert "decision" in text


@pytest.mark.asyncio
async def test_slash_bare_text_searches_and_enter_opens():
    from rac.explorer.screens.command import CommandScreen
    from rac.explorer.screens.context import ContextScreen

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"search feature")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, CommandScreen)  # results listed, surface open
        await pilot.press("enter")  # open the first (focused) result
        await pilot.pause()
        assert isinstance(app.screen, ContextScreen)


@pytest.mark.asyncio
async def test_slash_help_lists_registry_and_esc_closes():
    from textual.widgets import OptionList

    from rac.explorer.screens.command import CommandScreen
    from rac.explorer.screens.repository import RepositoryScreen

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"help")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, CommandScreen)
        results = app.screen.query_one(OptionList)
        assert results.option_count == 9  # the whole registry, nothing more
        await pilot.press("escape")
        assert isinstance(app.screen, RepositoryScreen)


@pytest.mark.asyncio
async def test_slash_home_pops_navigation_stack():
    from rac.explorer.screens.repository import RepositoryScreen

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")  # browser
        await pilot.press("enter")  # context
        await pilot.press("/")
        await pilot.press(*"home")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RepositoryScreen)


@pytest.mark.asyncio
async def test_slash_browse_with_type_filter():
    from textual.widgets import OptionList

    from rac.explorer.screens.browser import BrowserScreen

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"browse decision")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, BrowserScreen)
        artifact_list = app.screen.query_one(OptionList)
        assert artifact_list.option_count == 2  # the type header + one decision


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
async def test_h_binding_opens_health_screen():
    from textual.widgets import Static

    from rac.explorer.screens.health import HealthScreen
    from rac.explorer.screens.repository import RepositoryScreen

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")
        assert isinstance(app.screen, HealthScreen)
        overview = str(app.screen.query_one("#health-overview", Static).content)
        assert "Score" in overview
        assert "Completeness" in overview and "Coverage" in overview
        assert "✓ Healthy" in overview
        await pilot.press("escape")
        assert isinstance(app.screen, RepositoryScreen)


@pytest.mark.asyncio
async def test_slash_health_opens_health_screen():
    from rac.explorer.screens.health import HealthScreen

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"health")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, HealthScreen)


@pytest.mark.asyncio
async def test_health_attention_item_opens_context():
    from rac.explorer.screens.context import ContextScreen

    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")
        await pilot.pause()
        await pilot.press("enter")  # first attention item (focused)
        await pilot.pause()
        assert isinstance(app.screen, ContextScreen)


@pytest.mark.asyncio
async def test_slash_recommendations_opens_screen():
    from rac.explorer.screens.recommendations import RecommendationsScreen

    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("/")
        await pilot.press(*"recommendations")
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, RecommendationsScreen)
        from textual.widgets import OptionList

        listing = app.screen.query_one(OptionList)
        assert listing.option_count >= 1  # at least the broken-relationship finding


@pytest.mark.asyncio
async def test_health_r_opens_recommendations_and_item_opens_context():
    from rac.explorer.screens.context import ContextScreen
    from rac.explorer.screens.recommendations import RecommendationsScreen

    app = ExplorerApp(str(FIXTURES / "broken_rels"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("h")
        await pilot.pause()
        await pilot.press("r")  # health → recommendations
        await pilot.pause()
        assert isinstance(app.screen, RecommendationsScreen)
        await pilot.press("enter")  # first recommendation → its artifact
        await pilot.pause()
        assert isinstance(app.screen, ContextScreen)


@pytest.mark.asyncio
async def test_context_e_opens_external_editor(monkeypatch):
    from textual.widgets import Static

    import rac.explorer.editor as editor_mod

    launched: list[list[str]] = []
    monkeypatch.setattr(editor_mod, "_RUNNER", lambda cmd: launched.append(list(cmd)))
    monkeypatch.setenv("EDITOR", "code")

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")  # browser
        await pilot.press("enter")  # context
        await pilot.press("e")
        await pilot.pause()
        status = str(app.screen.query_one("#context-status", Static).content)
        assert "Opened" in status and "code" in status
        assert launched and launched[0][0] == "code"


@pytest.mark.asyncio
async def test_context_e_without_editor_shows_guidance(monkeypatch):
    from textual.widgets import Static

    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)

    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await _settled_panel_text(app, pilot)
        await pilot.press("enter")
        await pilot.press("enter")
        await pilot.press("e")
        await pilot.pause()
        status = str(app.screen.query_one("#context-status", Static).content)
        assert "No editor configured" in status


@pytest.mark.asyncio
async def test_slash_import_previews_then_confirms_write(tmp_path):
    from textual.widgets import Static

    from rac.explorer.screens.import_ import ImportScreen

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
        assert isinstance(app.screen, ImportScreen)
        panel = str(app.screen.query_one("#import-panel", Static).content)
        assert "Preview" in panel and "Imported Doc" in panel
        assert not target.exists()  # not written until confirmed

        await pilot.press("y")
        await pilot.pause()
        assert target.read_text(encoding="utf-8") == "# Imported Doc\n\nhello\n"
        assert "Imported" in str(app.screen.query_one("#import-panel", Static).content)


@pytest.mark.asyncio
async def test_slash_import_cancel_writes_nothing(tmp_path):
    from rac.explorer.screens.import_ import ImportScreen

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
        assert isinstance(app.screen, ImportScreen)
        await pilot.press("escape")  # cancel before confirming
        await pilot.pause()
        assert not target.exists()


@pytest.mark.asyncio
async def test_slash_import_reports_unsupported(tmp_path):
    from textual.widgets import Static

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
async def test_quit_binding_exits_cleanly():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("q")
    assert not app.is_running
