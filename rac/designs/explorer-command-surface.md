---
schema_version: 1
id: RAC-KTQ63DSJCAZ5
type: design
---
# Explorer Command Surface

## Context

RAC Explorer provides a terminal-native workspace for navigating product knowledge repositories.

Traditional command-line interfaces require users to remember commands:

```text
rac inspect

rac relationships

rac portfolio
```

Explorer should instead provide a discoverable interaction model where users express intent and navigate from a single entry point.

The command surface is inspired by modern developer tools such as:

- Claude Code
- Amp
- Command palettes
- Terminal-native workflows

---

## User Need

Users need a fast way to:

- Find artifacts
- Navigate repository knowledge
- Execute RAC workflows
- Discover available capabilities

without memorizing command syntax or navigating deep menus.

---

## Design

### Primary Interaction

The primary command entry point is:

```text
/
```

Typing `/` summons the command palette: a titled floating panel over the
context region with an input line on top and a navigable suggestion menu
directly below it. The idle frame carries no input chrome — the status line
advertises `/`. Esc dismisses the palette and restores the previous focus.

The menu is live:

- empty input offers the artifacts opened most recently in this repository
  (newest first, Enter reopens one) above the whole command registry,
  each group labelled (v0.8.9)
- a command prefix filters the registry
- any other text shows matching artifacts (quick-open) and a search hint

`↑ ↓` move the menu while typing stays in the input. Enter completes an
argument-taking command into the input, runs an argless one, opens a
highlighted artifact match, or routes bare text as a search. Large result
sets and ambiguous lookups render in the context region, so the layout
never jumps; artifact results there can be narrowed by type from the
keyboard — `f` cycles all → each type present → all (v0.8.9).

Example:

```text
/

open req-001

payments

validate repository

import document
```

---

## Unified Search and Commands

Search and actions share one interface.

The user should not need to decide:

```text
Am I searching?

or

Am I running a command?
```

Explorer resolves intent.

---

## Command Registry

All Explorer actions are registered through a single command registry.

Examples:

```text
open

search

validate

import

relationships

health
```

An action not registered in the command surface is considered undiscoverable.

---

## Artifact Navigation

Artifact lookup should support:

```text
REQ-001

ADR-004

payments
```

Results may include:

```text
Requirements

REQ-001 Payment Retry Logic


Decisions

ADR-004 Payment Provider Choice
```

---

## Operational Commands

Repository operations should be accessible.

Examples:

```text
/validate

/improve req-001

/import

/health

/schema decision
```

Explorer invokes RAC Core services.

Explorer does not implement operation logic.

Reference questions belong here too: `/schema` lists the registered
artifact types, and `/schema <type>` renders the type's expected structure
from the core schema registry (v0.8.9) — the same facts `rac schema`
reports.

---

## Keyboard Model

Primary:

```text
/      Summon the command palette (from anywhere)

↑ ↓    Navigate (menu while the palette is open)

Enter  Select / run / complete

Tab    Cycle panels

Esc    Back (palette → dismiss; context → view history; else → home)

q      Quit
```

Additional shortcuts may exist only for high-frequency actions.

Single-letter shortcuts are suspended while the palette input has focus, so
typed text is never mistaken for a binding.

---

## Empty States

The command surface should teach users.

Example:

```text
Start typing...

Try:

open req-001

validate

import document
```

---

## Constraints

### Single Interaction Model

Do not introduce:

- Separate search boxes
- Separate command palettes
- Feature-specific menus

The slash command is the universal entry point.

---

### No Intelligence Ownership

Command routing may happen in Explorer.

Repository answers come from RAC Core.

---

### Terminal Native

Interactions must work:

- Without mouse
- Over SSH
- In constrained terminals

---

## Accessibility

Command results shall not rely on colour alone.

Examples:

Preferred:

```text
✓ Valid

! Warning

✗ Error
```

Avoid:

```text
Green item

Yellow item

Red item
```

---

## Related Roadmaps

- v0.8.1-explorer-navigation
- v0.8.4-explorer-action-workflow
- v0.8.7-explorer-visual-overhaul
- v0.8.8-explorer-command-palette
- v0.8.9-explorer-live-workspace

---

## Related Decisions

- ADR-015
