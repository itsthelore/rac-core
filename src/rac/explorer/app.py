"""The Explorer Textual application (v0.8.0, restyled v0.8.7, ADR-028).

Keyboard-first and terminal-native: one persistent workspace frame
(:mod:`rac.explorer.screens.main`) with the rac-lantern theme as the curated
default. This is the first module on the import path that requires Textual;
:mod:`rac.explorer.launch` imports it lazily so the base install works
without the ``explorer`` extra.
"""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.screens.main import MainScreen
from rac.explorer.theme import RAC_LANTERN, THEME_NAME
from rac.explorer.widgets.commandbar import CommandBar


class ExplorerApp(App[None]):
    """Application shell over one repository: one frame, swappable views, `/`."""

    TITLE = "RAC Explorer"
    CSS_PATH = "explorer.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        # Not a priority binding: a typed `/` must keep working inside the
        # command bar's input rather than re-triggering this action.
        Binding("slash", "command_surface", "Commands"),
    ]

    def __init__(self, directory: str, recursive: bool = True) -> None:
        super().__init__()
        self.adapter = ExplorerAdapter(directory, recursive=recursive)
        self.sub_title = directory

    def on_mount(self) -> None:
        # The curated default (v0.8.7); the `theme` preference overrides it
        # with any Textual theme, and an unknown name never breaks startup.
        self.register_theme(RAC_LANTERN)
        try:
            self.theme = self.adapter.preferences.theme
        except Exception:  # noqa: BLE001 - unknown theme: keep the default
            self.theme = THEME_NAME
        self.adapter.record_open()  # workspace continuity (Initiative 1)
        self.push_screen(MainScreen(self.adapter))

    def action_command_surface(self) -> None:
        # `/` focuses the persistent bar from anywhere on the main screen;
        # there is no bar on the confirm-write modal.
        bars = self.screen.query(CommandBar)
        if bars:
            bars.first().focus()
