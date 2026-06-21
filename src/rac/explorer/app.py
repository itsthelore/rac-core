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
from rac.explorer.theme import RAC_THEMES, THEME_NAME
from rac.explorer.widgets.palette import CommandPalette


class ExplorerApp(App[None]):
    """Application shell over one repository: one frame, swappable views, `/`."""

    TITLE = "RAC Explorer"
    CSS_PATH = "explorer.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        # Not a priority binding: a typed `/` must keep working inside the
        # palette's input rather than re-triggering this action.
        Binding("slash", "command_surface", "Commands"),
    ]

    def __init__(self, directory: str, recursive: bool = True) -> None:
        super().__init__()
        self.adapter = ExplorerAdapter(directory, recursive=recursive)
        self.sub_title = directory

    def on_mount(self) -> None:
        # The curated pair (v0.26.0): rac-lantern (dark, the default) and
        # rac-parchment (light). The `theme` preference selects either, or any
        # other Textual theme, and an unknown name never breaks startup.
        for theme in RAC_THEMES:
            self.register_theme(theme)
        try:
            self.theme = self.adapter.preferences.theme
        except Exception:  # noqa: BLE001 - unknown theme: keep the default
            self.theme = THEME_NAME
        self.adapter.record_open()  # workspace continuity (Initiative 1)
        self.push_screen(MainScreen(self.adapter))

    def action_command_surface(self) -> None:
        # `/` summons the palette from anywhere on the main screen; there is
        # no palette on the confirm-write modal.
        palettes = self.screen.query(CommandPalette)
        if palettes:
            palettes.first().show()
