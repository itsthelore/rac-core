# Lore web — design system

The reference for the aesthetic is `design/mockup-landing.png`. The
tokens in `src/styles/tokens.css` are the single source of truth: no
hex value may appear anywhere else under `src/`.

## The five rules

1. **Three surfaces.** `--bg` (page), `--bg-panel` (containers),
   `--bg-element` (controls, key caps). Warm near-black, never pure
   black; text is dimmed (`--text` ≈ 10–13:1), never pure white.
2. **One hue dominates.** The lantern amber (`--accent`,
   `--accent-bright`, `--accent-muted`) is the only decorative colour.
   Teal and green are strictly semantic — teal for links and
   commands/tools, green for pass/check — never decoration.
3. **Dashed = container, solid = interactive.** Container chrome uses
   `--dash` / `--dash-subtle` (1px dashed). Anything you can press or
   type into uses solid borders (`--line`, `--line-active`) — key caps,
   listbox popovers, focused prompt bars.
4. **Mono everywhere.** JetBrains Mono (self-hosted woff2, weights
   400/700 only, `font-display: swap`) with a metric-compatible local
   fallback (`JetBrains Mono Fallback`, size-adjusted Courier New /
   Liberation Mono) so font loading causes no layout shift.
5. **Integer-scaled pixel art.** Pixel assets render with
   `image-rendering: pixelated` at whole-number multiples of their
   native size only (16×24 → 64×96, 96×144, …). Never fractional
   scales.

Radii are 0, except `--radius-key` (2px) on key caps. Sharp corners are
part of the look.

## Token adjustment for contrast

One token was adjusted from the palette ruling to meet WCAG AA (4.5:1)
for text. Lightness only; hue and saturation unchanged.

| Token     | Ruling    | Shipped   | Reason                                            |
| --------- | --------- | --------- | ------------------------------------------------- |
| `--error` | `#cb6f6f` | `#ce7878` | 4.48:1 on `--bg-element`; now 4.88:1 (L 62%→64%). |

All other ruling values shipped unchanged. `npm run contrast` audits
every used (text, surface) pair; `--accent-muted` and the border tokens
are excluded because they are never used as text.

## Mascot asset

The real mascot has landed: `design/lamplighter.png` — the hooded
lamplighter holding the lantern (500×395, transparent background). It
is high-resolution art, not pixel-grid, so it displays at 2x density
(250px CSS width) without the `.pixel-art` treatment. The generated
`design/lantern.png` (16×24, from `scripts/make-lantern.mjs`) remains
for the favicon and other small marks. Rule 5 — integer scaling — still
applies to true pixel-grid art such as the lantern.

## Fonts

JetBrains Mono Regular and Bold woff2 are vendored at
`src/assets/fonts/` with the OFL licence (`OFL.txt`). No other weights
or styles may be added without revisiting the performance budget.
