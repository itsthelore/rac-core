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

Typing `/` focuses the command bar — a persistent panel at the bottom of the
workspace frame, never hidden and never modal. Results and ambiguous lookups
render in the context region, so the layout never jumps.

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
```

Explorer invokes RAC Core services.

Explorer does not implement operation logic.

---

## Keyboard Model

Primary:

```text
/      Focus the command bar (from anywhere)

↑ ↓    Navigate

Enter  Select

Tab    Cycle panels

Esc    Back (bar → previous region; context → view history)

q      Quit
```

Additional shortcuts may exist only for high-frequency actions.

Single-letter shortcuts are suspended while the command bar has focus, so
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

---

## Related Decisions

- ADR-015
