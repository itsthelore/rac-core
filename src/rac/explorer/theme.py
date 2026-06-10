"""The rac-lantern theme — the Explorer's curated default (v0.8.7).

Derived from the mascot asset (``rac/assets/images/rac_explorer_mascot.png``):
a hooded explorer in warm amber on near-black, holding a lantern. The single
accent colour is that lantern amber on dark surfaces (DESIGN-visual-system).
The ``theme`` preference can select any other Textual theme; meaning never
depends on the palette (icons + labels + chips, ADR-028).
"""

from __future__ import annotations

from textual.theme import Theme

THEME_NAME = "rac-lantern"

RAC_LANTERN = Theme(
    name=THEME_NAME,
    primary="#F5A800",  # lantern amber — the one accent
    secondary="#D98E04",
    accent="#F5A800",
    warning="#F5A800",
    error="#E5484D",
    success="#46A758",
    foreground="#E8E2D5",
    background="#121110",  # near-black, as behind the mascot
    surface="#1A1916",  # Surface 1 — panels
    panel="#26231C",
    dark=True,
)
