"""Confirm-write modal — preview a file write, apply only on confirmation.

Any workflow that can change repository contents previews first and writes only
on explicit confirmation (ADR-024). Export findings uses this modal; import has
its own conversion step but the same discipline. It is the only surface that
lives on the screen stack over the persistent frame: a titled rounded panel
speaking the status line's key-chip language.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import ImportPreview
from rac.explorer.widgets.statusline import key_chips
from rac.explorer.widgets.views import render_preview


class ConfirmWriteScreen(ModalScreen[None]):
    """Show a write preview; `y` writes (never overwrites), Esc cancels."""

    BINDINGS = [
        Binding("y", "confirm", "Confirm"),
        Binding("escape", "back", "Cancel"),
    ]

    def __init__(self, adapter: ExplorerAdapter, preview: ImportPreview) -> None:
        super().__init__()
        self.adapter = adapter
        self.preview = preview
        # Write-once: `y` may repeat, but the file is written a single time.
        self._done = False

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-dialog") as dialog:
            dialog.border_title = f"Write {self.preview.target}"
            with VerticalScroll(id="confirm-scroll"):
                yield Static(render_preview(self.preview), id="confirm-panel")
            yield Static(key_chips((("y", "Confirm"), ("Esc", "Cancel"))), id="confirm-chips")

    def action_confirm(self) -> None:
        if self._done:
            return
        message = self.adapter.write_import(self.preview)
        self._done = True
        # The panel now reports the outcome; the only key left is Esc to leave.
        self.query_one("#confirm-panel", Static).update(message)
        self.query_one("#confirm-chips", Static).update(key_chips((("Esc", "Back"),)))

    def action_back(self) -> None:
        self.app.pop_screen()
