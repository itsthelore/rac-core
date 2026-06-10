"""The Explorer mascot — a lantern-carrying guide (v0.8.6).

A small explorer with a lantern: navigation that illuminates hidden product
knowledge (DESIGN-mascot). The mascot is identity, never a feature — it gates
nothing and modifies nothing. Each state carries equivalent text, so disabling
animations (static frame) or the mascot entirely (text only) loses no
information (DESIGN-mascot-animations, ADR-028). This module never imports
Textual.
"""

from __future__ import annotations

# Mascot states tied to system events (DESIGN-mascot-animations).
IDLE = "idle"
SEARCHING = "searching"
DISCOVERY = "discovery"
SUCCESS = "success"
EMPTY = "empty"
ERROR = "error"

# A lantern glyph per state — the "animated" element is the lantern; with
# animations off we use the steady frame. Meaning never rides on the glyph
# alone; the label below always accompanies it.
_LANTERN = {
    IDLE: "◇",
    SEARCHING: "◈",
    DISCOVERY: "✶",
    SUCCESS: "✓",
    EMPTY: "○",
    ERROR: "✗",
}

# The text that carries each state's meaning without any glyph (accessibility).
_LABEL = {
    IDLE: "Ready to explore.",
    SEARCHING: "Searching…",
    DISCOVERY: "Found something.",
    SUCCESS: "Done.",
    EMPTY: "Nothing here yet.",
    ERROR: "Something went wrong.",
}


def label(state: str) -> str:
    """The text-only feedback for ``state`` (always available)."""
    return _LABEL.get(state, _LABEL[IDLE])


def figure(state: str, *, animations: bool = True) -> str:
    """The mascot as terminal art for ``state``.

    ``animations`` selects the lantern glyph for the state; when False the
    steady idle lantern is used. The accompanying label is always returned, so
    no information depends on the glyph.
    """
    lantern = _LANTERN.get(state, _LANTERN[IDLE]) if animations else _LANTERN[IDLE]
    return "\n".join(
        [
            "   ___",
            "  /^^^\\",
            f"  (• •)  {lantern}",
            "  /| |\\  |",
            f"  guide · {label(state)}",
        ]
    )
