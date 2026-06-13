"""The Explorer mascot — a lantern-carrying guide (v0.8.6, animated v0.8.8,
interactive v0.8.12).

A small explorer with a lantern: navigation that illuminates hidden product
knowledge (DESIGN-mascot). The mascot is identity, never a feature — it gates
nothing and modifies nothing.

Each state is a *frame sequence* (DESIGN-mascot-animations): equal-width,
equal-height blocks of terminal art cycled on a slow timer by the widget that
shows them. Artwork is data — replacing the strings in :data:`FRAMES` changes
the animation and nothing else. Every state carries equivalent text, so
disabling animations (first frame only) or the mascot entirely (text only)
loses no information (ADR-028).

Selecting the mascot returns a small response (DESIGN-mascot-interaction):
:func:`interaction_message` maps the Nth selection to an acknowledgement,
rotating discovery messages, occasional workflow guidance, and one rare line.
Responses are data and the mapping is pure, so they surface existing
functionality without containing any. This module never imports Textual.
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


# --- interaction (DESIGN-mascot-interaction) ---------------------------------
#
# Selecting the mascot rewards curiosity without interrupting work: a small
# acknowledgement, occasional discovery messages, gentle guidance toward
# existing commands, and one rare line. None of these unlock features or touch
# the repository — the mascot surfaces functionality, it does not contain it.

#: The default acknowledgement for a single selection.
ACK = "Still exploring."

#: Occasional reminders of why product knowledge is worth keeping.
DISCOVERY_MESSAGES = (
    "Context preserved.",
    "Future teams will thank you.",
    "Remember why it changed.",
)

#: Guidance that points at existing Explorer commands (it names them; it is
#: not a way to run them).
GUIDANCE = "Try:  /inspect  /relationships  /health"

#: The rare response, reached only on repeated selection.
RARE = "You found the lantern."

#: The selection count at which the rare response appears.
RARE_AT = 7

#: Guidance appears on every Nth selection.
_GUIDANCE_EVERY = 4


def interaction_message(count: int) -> str:
    """The response for the ``count``-th mascot selection (1-based).

    Deterministic, so the whole interaction is testable without a terminal:
    the acknowledgement comes first, the rare line lands at exactly
    :data:`RARE_AT`, guidance recurs on a fixed cadence, and the discovery
    messages rotate otherwise. No randomness, no Textual.
    """
    if count <= 1:
        return ACK
    if count == RARE_AT:
        return RARE
    if count % _GUIDANCE_EVERY == 0:
        return GUIDANCE
    return DISCOVERY_MESSAGES[(count - 2) % len(DISCOVERY_MESSAGES)]
