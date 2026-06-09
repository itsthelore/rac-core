# Explorer Health Model

## Context

RAC Core provides repository intelligence including:

- Validation
- Relationships
- Completeness
- Portfolio analysis

Explorer surfaces this information to help users understand repository quality.

Explorer does not calculate health.

It visualizes Core-owned intelligence.

---

## User Need

Users need to quickly answer:

```text
Is this repository healthy?

What needs attention?

Where should I focus?
```

without manually interpreting multiple reports.

---

## Design

Explorer shall provide a repository health experience.

Example:

```text
Repository Health

Score

92%


Attention

2 broken relationships

1 incomplete requirement
```

---

## Attention Items

Issues should be:

- Actionable
- Linked to artifacts
- Prioritized

Example:

```text
REQ-004

Missing Success Metrics


Open →
```

---

## Health Areas

Possible categories:

```text
Completeness

Relationships

Validation

Coverage
```

Final scoring remains owned by RAC Core.

---

## Constraints

Explorer shall not:

- Calculate scores
- Invent recommendations
- Override Core diagnostics

---

## Accessibility

Health indicators shall not rely on colour.

Example:

Good:

```text
✓ Healthy

! Needs Attention

✗ Error
```

Avoid:

```text
Green

Yellow

Red
```

---

## Related Roadmaps

- v0.9.0-explorer-foundation
- v0.9.2-knowledge-operations

---

## Related Decisions

- ADR-015
