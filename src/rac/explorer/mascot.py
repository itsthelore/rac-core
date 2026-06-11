"""The Explorer mascot — a lantern-carrying guide (v0.8.6, animated v0.8.8).

A small explorer with a lantern: navigation that illuminates hidden product
knowledge (DESIGN-mascot). The mascot is identity, never a feature — it gates
nothing and modifies nothing.

Each state is a *frame sequence* (DESIGN-mascot-animations): equal-width,
equal-height blocks of terminal art cycled on a slow timer by the widget that
shows them. Artwork is data — replacing the strings in :data:`FRAMES` changes
the animation and nothing else. Every state carries equivalent text, so
disabling animations (first frame only) or the mascot entirely (text only)
loses no information (ADR-028). This module never imports Textual.
"""

from __future__ import annotations

# Mascot states tied to system events (DESIGN-mascot-animations).
IDLE = "idle"
SEARCHING = "searching"
DISCOVERY = "discovery"
SUCCESS = "success"
EMPTY = "empty"
ERROR = "error"

# The text that carries each state's meaning without any art (accessibility).
_LABEL = {
    IDLE: "Ready to explore.",
    SEARCHING: "Searching…",
    DISCOVERY: "Found something.",
    SUCCESS: "Done.",
    EMPTY: "Nothing here yet.",
    ERROR: "Something went wrong.",
}


def _figure_frame(lantern: str, eyes: str = "• •") -> str:
    """One frame of the hooded explorer; the lantern is the animated element."""
    return "\n".join(
        [
            "   ___   ",
            "  /^^^\\  ",
            f"  ({eyes})  {lantern}",
            "  /| |\\  |",
        ]
    )


def _pad(*frames: str) -> tuple[str, ...]:
    """Space-pad ``frames`` to one width and height so cycling never jitters."""
    split = [frame.split("\n") for frame in frames]
    height = max(len(lines) for lines in split)
    width = max(len(line) for lines in split for line in lines)
    return tuple(
        "\n".join((lines + [""] * (height - len(lines)))[i].ljust(width) for i in range(height))
        for lines in split
    )


# State → frame sequence. Placeholder art (v0.8.8): the lantern flickers and
# the eyes blink; final frames arrive as drop-in replacements for these
# strings. Calm states (success, error) hold a single frame by design.
FRAMES: dict[str, tuple[str, ...]] = {
    IDLE: _pad(_figure_frame("◇"), _figure_frame("◆"), _figure_frame("◇", eyes="– –")),
    SEARCHING: _pad(_figure_frame("◈"), _figure_frame("◇"), _figure_frame("◆")),
    DISCOVERY: _pad(_figure_frame("✶"), _figure_frame("✦"), _figure_frame("✶")),
    SUCCESS: _pad(_figure_frame("✓")),
    EMPTY: _pad(_figure_frame("○"), _figure_frame("◌")),
    ERROR: _pad(_figure_frame("✗")),
}


def label(state: str) -> str:
    """The text-only feedback for ``state`` (always available)."""
    return _LABEL.get(state, _LABEL[IDLE])


def frames(state: str) -> tuple[str, ...]:
    """The frame sequence for ``state`` (at least one frame)."""
    return FRAMES.get(state, FRAMES[IDLE])


def figure(state: str, frame: int = 0, *, animations: bool = True) -> str:
    """The mascot art for ``state`` at ``frame``, with its label attached.

    With ``animations`` off the steady first frame is used. The label is
    always part of the figure, so no information depends on the art.
    """
    sequence = frames(state)
    art = sequence[frame % len(sequence)] if animations else sequence[0]
    return f"{art}\n  guide · {label(state)}"
