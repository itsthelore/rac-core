"""The Explorer Textual application shell (ADR-028).

Keyboard-first and terminal-native: one persistent workspace frame
(:class:`rac.explorer.screens.main.MainScreen`) over a single repository, with
the rac-lantern theme as the curated default. This is the first module on the
import path to require Textual; :mod:`rac.explorer.launch` imports it lazily so
the base install runs without the ``explorer`` extra.
"""

from __future__ import annotations

from textual.app import App
from textual.binding import Binding

from rac.explorer.adapter import ExplorerAdapter
from rac.explorer.screens.main import MainScreen
from rac.explorer.theme import RAC_THEMES, THEME_NAME
from rac.explorer.widgets.palette import CommandPalette


class ExplorerApp(App[None]):
    """The application shell: one frame, swappable views, and the ``/`` surface."""

    TITLE = "RAC Explorer"
    CSS_PATH = "explorer.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        # Deliberately not a priority binding: a typed `/` must keep reaching
        # the palette's input as text rather than re-triggering this action.
        Binding("slash", "command_surface", "Commands"),
    ]

    def __init__(self, directory: str, recursive: bool = True) -> None:
        super().__init__()
        self.adapter = ExplorerAdapter(directory, recursive=recursive)
        self.sub_title = directory

    def on_mount(self) -> None:
        # Register the curated themes so all appear in the `/settings` cycle,
        # then adopt the `theme` preference. An unknown or unregistered theme
        # name must never break startup, so any failure falls back to the
        # default rather than propagating.
        for theme in RAC_THEMES:
            self.register_theme(theme)
        try:
            self.theme = self.adapter.preferences.theme
        except Exception:  # noqa: BLE001 — unknown theme: keep the default
            self.theme = THEME_NAME
        self.adapter.record_open()  # workspace continuity (Initiative 1)
        self.push_screen(MainScreen(self.adapter))

    def action_command_surface(self) -> None:
        # `/` summons the palette from anywhere on the main screen; the
        # confirm-write modal has no palette, so query rather than assume one.
        palettes = self.screen.query(CommandPalette)
        if palettes:
            palettes.first().show()
