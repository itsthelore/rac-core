---
schema_version: 1
id: RAC-KTQ63DT43E1Y
type: design
---
# Explorer Visual System

## Context

RAC Explorer should feel like a modern developer tool while remaining terminal native.

The visual reference is Posting (posting.sh) and the Textual demo, guided by five principles:

- GitHub information architecture
- Linear spacing
- Notion content focus
- LazyGit keyboard UX
- Textual implementation

## User Need

Users need a calm, information-dense interface for understanding complex repositories.

## Design

### Canonical Frame

One persistent workspace frame; navigation swaps the context region only.

```text
 RAC Explorer 0.8.8                                      ~/work/payments
╭─ Artifacts ─────────────╮╭─ REQ-004 — Checkout flow ───────────────╮
│ ▾ Requirements     12   ││ Content │ Inspection │ Links (3) │ Fin… │
│   REQ Checkout flow     ││                                         │
│   REQ Refund handling   ││  # Checkout flow                        │
│ ▸ Decisions         8   ││                                         │
│ ▸ Roadmaps          5   ││  ## Problem                             │
│ ▸ Prompts           7   ││  Retail investors struggle to…          │
│                         ││                                         │
╰─ ✓ Valid · 3 links ─────╯╰─────────────────────────────────────────╯
 ⏎ Open  ⇥ Panel  e Edit  h Health  / Commands     ✓ Healthy 92 · 84 links
```

Pressing `/` summons the command palette over the context region:

```text
      ╭─ / ────────────────────────────────────────────────╮
      │ open chec_                                         │
      │                                                    │
      │  /open <ref>      Open an artifact by ID or alias  │
      │  REQ Checkout flow                ✓ Valid          │
      │  Enter searches for 'open chec'                    │
      ╰────────────────────────────────────────────────────╯
```

### Regions

Stable regions, top to bottom:

App bar:
one plain line — application name and version in the accent colour on the left, repository path on the right. No stock Header.

Navigation sidebar:
a titled rounded panel ("Artifacts") fixed at 28 cells, hidden below 80 columns. Hosts the artifact tree, which mirrors the repository's directory structure by default (v0.8.10): directory rows show the name with a trailing `/` and a dim artifact count; type and flat groupings remain as settings. Artifact rows show the type tag and the artifact title (ID only when untitled); invalid artifacts carry a `✗` marker beside the tag.

Context panel:
a titled rounded panel hosting exactly one view at a time (home, artifact context, health, recommendations, import, results, settings). When an artifact is open, the panel title is its `ID — title`.

Status line:
one row of key-chip hints with status right-aligned. No stock Footer. The `/` chip advertises the palette.

Command palette (summoned):
a titled rounded panel floated over the context region on its own layer — input on top, suggestion menu below. Hidden when idle; the frame carries no input chrome. ~80 cells wide, centred, menu capped near 14 rows.

### Surfaces

Three depth levels:

Surface 0:
application background.

Surface 1:
panels — `border: round` in a muted colour, `background: $surface`, `padding: 1 2`.

Surface 2:
the focused panel — its border switches to `round $accent`.

Panels may carry a one-line border-bottom status, like the sidebar showing the selected artifact's status chip.

### Colour

Single accent colour.

Colour communicates focus, not meaning: the focused panel border, the selected row, the `/` glyph, and the app-bar title.

Type tags carry one hue per artifact type (`REQ` `ADR` `RMP` `PRM` `DSG`), always rendered next to the name text so meaning never rides on colour alone.

### Theme

The default theme is "rac-lantern", derived from the Explorer mascot asset
(`rac/assets/images/rac_explorer_mascot.png`): lantern amber (the `#F5A800`
family) as the single accent on near-black surfaces.

The `theme` preference selects any other Textual theme. All meaning survives
any theme — icons, labels, and chips carry state, never colour alone.

### Content

The context panel hosts tabs: `Content │ Inspection │ Links │ Findings`.
Links and Findings carry count badges when populated.

Content is the default tab and renders the document's Markdown, read-only —
the Explorer presents the knowledge itself, not only structural metadata.
The document scrolls under the keyboard (the pane takes focus on open), the
column is capped near 96 cells for readability, and artifact references in
the text are navigable: activating one resolves it and opens the target in
place, with Esc walking back. Inspection carries status, completeness, and
diagnostics; Links carries relationships, impact, and lineage; Findings
carries the artifact's recommendations.

### Spacing

Generous but tight:

- label columns align at 12 cells
- a blank line separates groups
- panels keep `padding: 1 2`
- scrollbars are muted; the accent never rides a scrollbar

### Status Chips

Short inverse-video chips for states, with one casing everywhere:

```text
✓ Valid

! 2 Warnings
```

The status line right-aligns the repository health chip and link count.
Hints live in chips, never duplicated as panel text; loading is one calm
line of phase and count; empty results use the mascot's empty state.

### Interaction

Primary:

/

summons the command palette from anywhere.

Secondary:

keyboard shortcuts.

Focus model:

- `Esc` dismisses the palette back to the previous region; in the context panel it steps back through view history; with no history it returns home — never a dead-end
- `Tab` cycles panels
- single-letter shortcuts are suspended while the palette input has focus
- `?` opens the command help

## Constraints

- Terminal compatibility
- 256 colour fallback
- No colour-only meaning
- Keyboard first
- One stable frame; views swap inside the context region, the layout never jumps
- No stock Textual Header or Footer
- Read-only content rendering; editing belongs to external tools

## Accessibility

Validation state uses:

icons + labels + colour

Type tags and key chips always carry text; disabling colour loses no meaning.

## Related Roadmaps

- v0.8.7-explorer-visual-overhaul
- v0.8.8-explorer-command-palette
- v0.8.10-explorer-create-and-stats
