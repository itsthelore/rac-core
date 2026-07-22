---
schema_version: 1
id: RAC-KTQ63DSN8C50
type: design
---
# Explorer First Run Experience

## Context

RAC Explorer introduces a new way of interacting with product knowledge repositories.

The CLI is optimized for automation:

```text
Run command

Receive output
```

Explorer is optimized for exploration:

```text
Enter workspace

Understand repository

Navigate knowledge
```

The first launch experience determines whether users understand this distinction.

---

## User Need

Users need to become productive without knowing:

- RAC commands
- Repository structure
- Artifact types
- Relationship concepts

Explorer should guide users from zero context to useful exploration.

---

## Design

## First Launch

Running:

```bash
rac explorer
```

without previous context opens onboarding.

Example:

```text
Welcome to RAC Explorer

Your product knowledge workspace.


Choose repository:

> Current directory

  Recent repository

  Browse
```

---

## Repository Discovery

Explorer checks the selected location.

Possible states:

---

### Existing RAC Repository

Example:

```text
Repository Found

Analyzing...

✓ Requirements 42

✓ Decisions 12

✓ Relationships 84


Press / for anything
```

---

### Empty Repository

Example:

```text
No RAC artifacts found.


Start by:

> Import documents

  Create artifact

  Open another repository
```

---

### Invalid Repository

Example:

```text
Repository issues found


3 invalid artifacts

2 broken relationships


Open anyway?

> Yes

  View issues
```

---

## Learning The Interface

Onboarding teaches only essential controls.

Example:

```text
Navigation

/      Search and commands

↑ ↓    Move

Enter  Open

q      Quit
```

Do not introduce every feature upfront.

---

## Recent Repositories

Explorer remembers previously opened repositories.

Example:

```text
Recent

requirements-as-code

payments-platform

identity-service
```

---

## Returning Users

Skip onboarding.

Restore:

- Last repository
- Last view
- Last artifact

Users return directly to work.

---

## Preferences

Optional preferences:

- Theme
- Default start view
- Artifact grouping

Preferences must never block onboarding.

---

## Constraints

### Fast Startup

Users should reach repository context within seconds.

---

### No Accounts

Explorer requires:

- No login
- No cloud connection
- No synchronization

---

### No Forced Setup

A user can always exit onboarding and manually navigate.

---

## Accessibility

The onboarding flow shall:

- Be keyboard navigable
- Avoid colour-only status
- Provide clear text states

---

## Related Roadmaps

- v0.8.1-explorer-navigation

---

## Related Decisions

- ADR-015
