"""Browser screen — every artifact in the repository, grouped by type (v0.8.1).

Renders the loaded repository model only (no Core operations run here); Enter
opens an artifact's context view, Esc returns to the previous screen.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Header, OptionList
from textual.widgets.option_list import Option

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.state import BrowserState

from .context import ContextScreen


class BrowserScreen(Screen[None]):
    """Keyboard-first artifact list: ↑↓ navigate, Enter opens, Esc backs."""

    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, adapter: ExplorerAdapter, browser: BrowserState) -> None:
        super().__init__()
        self.adapter = adapter
        self.browser = browser

    def compose(self) -> ComposeResult:
        yield Header()
        # A None entry renders as a separator line between type groups.
        options: list[Option | None] = []
        for artifact_type, rows in self.browser.groups:
            if options:
                options.append(None)
            options.append(Option(f"{artifact_type} ({len(rows)})", id=None, disabled=True))
            for row in rows:
                title = row.title or row.id
                options.append(Option(f"  {row.status_label}  {title}", id=row.path))
        option_list = OptionList(*options, id="artifact-list")
        option_list.border_title = f"Artifacts ({self.browser.total})"
        yield option_list
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is None:
            return
        context = self.adapter.context_state(event.option_id)
        if context is not None:
            self.app.push_screen(ContextScreen(context))

    def action_back(self) -> None:
        self.app.pop_screen()
