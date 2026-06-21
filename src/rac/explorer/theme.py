"""The curated RAC themes — a dark default and a light companion (v0.26.0).

Both derive from the mascot asset (``rac/assets/images/rac_explorer_mascot.png``):
a hooded explorer carrying a lantern, the single accent colour the lantern amber
(DESIGN-visual-system). ``rac-lantern`` is the dark default — amber on near-black,
as behind the mascot — and ``rac-parchment`` is the light companion — the same
lantern on warm paper, the amber deepened so it stays legible on light.

The ``theme`` preference can select either, or any other registered Textual
theme; meaning never depends on the palette (icons + labels + chips, ADR-028),
so the whole interface recolours from these tokens with no loss of information.
"""

from __future__ import annotations

from textual.theme import Theme

THEME_NAME = "rac-lantern"
PARCHMENT_NAME = "rac-parchment"

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

RAC_PARCHMENT = Theme(
    name=PARCHMENT_NAME,
    primary="#B6770A",  # the lantern amber, deepened to read on paper
    secondary="#8C6A2A",
    accent="#B6770A",
    warning="#B6770A",
    error="#C0362C",
    success="#3E7D2E",
    foreground="#2A2520",  # dark ink
    background="#F4EEE1",  # warm paper
    surface="#FBF7EC",  # Surface 1 — panels, a touch lighter than the canvas
    panel="#EBE3D2",
    dark=False,
)

# The curated pair, registered together so both appear in the `/settings`
# theme cycle and sort adjacently under the `rac-` prefix.
RAC_THEMES = (RAC_LANTERN, RAC_PARCHMENT)
