# Explorer Knowledge Graph

## Context

RAC repositories contain connected product knowledge.

Artifacts are related through:

- Requirements
- Decisions
- Roadmaps
- Prompts
- Designs

Relationships allow users to understand why artifacts exist and how changes propagate.

---

## User Need

Users need to answer:

```text
Why does this exist?

What depends on this?

What happens if this changes?
```

without manually following links across files.

---

## Design

Explorer shall provide relationship-based navigation.

Initial views may be textual rather than graphical.

Example:

```text
ROADMAP-Q3

    ↓

REQ-004

    ↓

ADR-012
```

---

## Impact View

Users should understand downstream dependencies.

Example:

```text
Impact Analysis

Changing:

ADR-012


May affect:

REQ-004

PROMPT-007
```

---

## Lineage View

Users should understand artifact evolution.

Example:

```text
REQ-004


Created

↓

Updated

↓

Superseded
```

---

## Constraints

- Relationship intelligence belongs to RAC Core
- Explorer only visualizes relationships
- Terminal readability takes priority over graphical complexity

---

## Non Goals

- Interactive canvas
- Web-style graph editor
- Manual relationship editing

---

## Related Requirements

- v0.9.3 Intelligence Views

---

## Related Decisions

- ADR-015 Explorer as Core Consumer