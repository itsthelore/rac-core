"""The status line — key-chip hints and repository status (v0.8.7).

Replaces the stock Footer (DESIGN-visual-system): compact inverse-video key
chips on the left, context-sensitive to the focused panel (LazyGit UX), with
the health chip and link count right-aligned. Every chip carries a text
label, so nothing depends on the chip styling (ADR-028).
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from rac.explorer.state import RepositorySummaryState, health_label

# Focused region → the key hints that matter there.
_HINTS: dict[str, tuple[tuple[str, str], ...]] = {
    "home": (
        ("⏎", "Browse"),
        ("h", "Health"),
        (".", "Resume"),
        ("/", "Commands"),
        ("q", "Quit"),
    ),
    "sidebar": (
        ("⏎", "Open"),
        ("⇥", "Panel"),
        ("/", "Commands"),
        ("q", "Quit"),
    ),
    "context": (
        ("e", "Edit"),
        ("g", "Links"),
        ("Esc", "Back"),
        ("/", "Commands"),
        ("q", "Quit"),
    ),
    "health": (
        ("⏎", "Open"),
        ("r", "Recommendations"),
        ("Esc", "Back"),
        ("/", "Commands"),
    ),
    "recommendations": (
        ("⏎", "Open"),
        ("x", "Export"),
        ("Esc", "Back"),
        ("/", "Commands"),
    ),
    "import": (("y", "Confirm"), ("Esc", "Back")),
    "results": (("⏎", "Open"), ("Esc", "Back"), ("/", "Commands")),
    "command": (("⏎", "Run"), ("Esc", "Back")),
}


def key_chips(pairs: tuple[tuple[str, str], ...]) -> Text:
    """Render (key, label) pairs as inverse-video chips with text labels.

    Shared with the confirm-write modal so every surface speaks the same
    hint language (DESIGN-visual-system).
    """
    text = Text()
    for key, label in pairs:
        if text:
            text.append("  ")
        text.append(f" {key} ", style="reverse")
        text.append(f" {label}")
    return text


class StatusLine(Horizontal):
    """Key chips left, health chip and link count right."""

    def __init__(self) -> None:
        super().__init__(id="status-line")

    def compose(self) -> ComposeResult:
        yield Static(id="status-hints")
        yield Static(id="status-right")

    def show_hints(self, region: str) -> None:
        pairs = _HINTS.get(region, _HINTS["home"])
        self.query_one("#status-hints", Static).update(key_chips(pairs))

    def show_summary(self, summary: RepositorySummaryState) -> None:
        text = Text()
        text.append(
            f" {health_label(summary.health_score)} {summary.health_score} ", style="reverse"
        )
        text.append(f" · {summary.relationship_total} links")
        self.query_one("#status-right", Static).update(text)
