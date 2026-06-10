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
from rac.explorer.screens.command import CommandScreen
from rac.explorer.screens.repository import RepositoryScreen


class ExplorerApp(App[None]):
    """Application shell over one repository: home, browser, context, `/`."""

    TITLE = "RAC Explorer"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("slash", "command_surface", "Commands"),
    ]
    CSS = """
    RepositoryPanel {
        padding: 1 2;
    }
    #context-panel {
        padding: 1 2;
    }
    CommandScreen {
        align: center top;
    }
    #command-surface {
        width: 80%;
        max-height: 70%;
        margin: 2 4;
        padding: 1 2;
        background: $surface;
        border: solid $accent;
    }
    """

    def __init__(self, directory: str, recursive: bool = True) -> None:
        super().__init__()
        self.adapter = ExplorerAdapter(directory, recursive=recursive)
        self.sub_title = directory

    def on_mount(self) -> None:
        # Preferences (v0.8.6): apply the theme if Textual recognizes it;
        # an unknown theme name must never break startup.
        try:
            self.theme = self.adapter.preferences.theme
        except Exception:  # noqa: BLE001 - unknown theme: keep the default
            pass
        self.adapter.record_open()  # workspace continuity (Initiative 1)
        self.push_screen(RepositoryScreen(self.adapter))

    def action_command_surface(self) -> None:
        if isinstance(self.screen, CommandScreen):
            return
        self.push_screen(CommandScreen(self.adapter))
