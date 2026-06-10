"""The app bar — one plain line above the panels (v0.8.7).

``RAC Explorer <version>`` in the accent colour on the left, the repository
path on the right, replacing the stock Textual Header (DESIGN-visual-system).
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from rac import __version__


class AppBar(Horizontal):
    """Application identity left, repository path right."""

    def __init__(self, directory: str) -> None:
        super().__init__(id="appbar")
        self._directory = directory

    def compose(self) -> ComposeResult:
        yield Static(f"RAC Explorer {__version__}", id="appbar-title")
        yield Static(self._directory, id="appbar-path")
