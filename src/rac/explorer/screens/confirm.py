"""Confirm-write screen — preview a file write, apply only on confirmation (v0.8.4).

Any workflow that can change repository contents previews first and writes only
on explicit confirmation (Initiative 4, ADR-024). Used to export findings;
import has its own conversion step but the same confirm discipline.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import ImportPreview
from rac.explorer.widgets.views import render_preview


class ConfirmWriteScreen(Screen[None]):
    """Show a write preview; `y` writes (never overwrites), Esc cancels."""

    BINDINGS = [
        Binding("y", "confirm", "Confirm"),
        Binding("escape", "back", "Cancel"),
    ]

    def __init__(self, adapter: ExplorerAdapter, preview: ImportPreview) -> None:
        super().__init__()
        self.adapter = adapter
        self.preview = preview
        self._done = False

    def compose(self) -> ComposeResult:
        yield Static(render_preview(self.preview), id="confirm-panel")

    def action_confirm(self) -> None:
        if self._done:
            return
        message = self.adapter.write_import(self.preview)
        self._done = True
        self.query_one("#confirm-panel", Static).update(f"{message}\n\nPress Esc to go back.")

    def action_back(self) -> None:
        self.app.pop_screen()
