"""Headless screen tests for the Explorer shell (v0.8.0, ADR-027).

Runs the Textual app through ``App.run_test()`` (no real terminal). Worker
results are awaited via ``app.workers.wait_for_complete()`` before asserting,
keeping the thread-worker tests deterministic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from rac.explorer.app import ExplorerApp
from rac.explorer.widgets import RepositoryPanel

FIXTURES = Path(__file__).parent / "fixtures" / "portfolio_summary"


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
    assert _health_label(60) == "! Needs attention"
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
async def test_quit_binding_exits_cleanly():
    app = ExplorerApp(str(FIXTURES / "valid_clean"))
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.press("q")
    assert not app.is_running
