"""The curated RAC themes — dark, light, and high-contrast (v0.26.0, v0.26.1).

All derive from the mascot asset (``rac/assets/images/rac_explorer_mascot.png``):
a hooded explorer carrying a lantern, the single accent colour the lantern amber
(DESIGN-visual-system). ``rac-lantern`` is the dark default — amber on near-black,
as behind the mascot; ``rac-parchment`` is the light companion — the same lantern
on warm paper, the amber deepened so it stays legible on light; and
``rac-high-contrast`` maximises separation — pure-white ink on true black with a
brighter amber, for low-vision and bright-environment use.

The ``theme`` preference can select any of these, or any other registered Textual
theme; meaning never depends on the palette (icons + labels + chips, ADR-028),
so the whole interface recolours from these tokens with no loss of information.
"""

from __future__ import annotations

from textual.theme import Theme

THEME_NAME = "rac-lantern"
PARCHMENT_NAME = "rac-parchment"
HIGH_CONTRAST_NAME = "rac-high-contrast"

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

RAC_HIGH_CONTRAST = Theme(
    name=HIGH_CONTRAST_NAME,
    primary="#FFB224",  # a brighter lantern amber for maximum separation
    secondary="#FFC861",
    accent="#FFB224",
    warning="#FFB224",
    error="#FF5A5F",
    success="#3FE08F",
    foreground="#FFFFFF",  # pure white ink
    background="#000000",  # true black
    surface="#0A0A0A",
    panel="#3D3D3D",  # a clearly visible panel border
    dark=True,
)

# The curated themes, registered together so all appear in the `/settings`
# theme cycle and sort adjacently under the `rac-` prefix: the dark default,
# the light companion, and a high-contrast option (v0.26.1).
RAC_THEMES = (RAC_LANTERN, RAC_PARCHMENT, RAC_HIGH_CONTRAST)
