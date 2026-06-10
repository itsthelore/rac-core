"""The Explorer Textual application (v0.8.0, ADR-028).

Keyboard-first and terminal-native: the footer surfaces the bindings, and the
shell stays responsive because every Core operation runs through workers
(see :mod:`rac.explorer.screens.repository`). This is the first module on the
import path that requires Textual; :mod:`rac.explorer.launch` imports it
lazily so the base install works without the ``explorer`` extra.
"""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.screens.repository import RepositoryScreen


class ExplorerApp(App[None]):
    """Application shell over one repository (navigation arrives in v0.8.1)."""

    TITLE = "RAC Explorer"
    BINDINGS = [Binding("q", "quit", "Quit")]
    CSS = """
    RepositoryPanel {
        padding: 1 2;
    }
    """

    def __init__(self, directory: str, recursive: bool = True) -> None:
        super().__init__()
        self.adapter = ExplorerAdapter(directory, recursive=recursive)
        self.sub_title = directory

    def on_mount(self) -> None:
        self.push_screen(RepositoryScreen(self.adapter))
