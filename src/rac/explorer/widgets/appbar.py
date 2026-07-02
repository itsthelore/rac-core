"""The app bar — one plain line above the panels (v0.8.7).

``RAC Explorer <version>`` in the accent colour on the left, the repository
path on the right, standing in for the stock Textual Header
(DESIGN-visual-system).
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from rac import __version__

# The released version only — a local-build suffix (``+g<hash>``) is noise on
# the bar, and the pinned parse keeps it out (tests assert no "+" survives).
_SHORT_VERSION = __version__.partition("+")[0]


def _tilde(directory: str) -> str:
    """Contract the home directory to ``~`` for display; leave others as-is.

    A path outside ``$HOME`` has no home-relative form, so ``relative_to``
    raises and we fall back to the directory verbatim.
    """
    try:
        return f"~/{Path(directory).expanduser().relative_to(Path.home())}"
    except ValueError:
        return directory


class AppBar(Horizontal):
    """Application identity on the left, repository path on the right."""

    def __init__(self, directory: str) -> None:
        super().__init__(id="appbar")
        self._directory = directory

    def compose(self) -> ComposeResult:
        yield Static(f"RAC Explorer {_SHORT_VERSION}", id="appbar-title")
        yield Static(_tilde(self._directory), id="appbar-path")
