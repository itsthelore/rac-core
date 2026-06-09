---
schema_version: 1
id: RAC-KTQ63DRA31YC
type: decision
---
# ADR-020: Requirements as Long-Lived Product Capabilities

## Status

Accepted

## Context

RAC uses structured Markdown artifacts to describe product knowledge.

The repository now contains multiple artifact types:

- Requirements
- Roadmaps
- ADRs
- Designs
- Prompts

During early development, RAC primarily used roadmap artifacts to drive implementation.

Roadmaps successfully captured:

- Release scope
- Delivery sequencing
- Implementation plans
- Version history

However, relying only on roadmaps risks treating delivery plans as the source of product intent.

A roadmap explains:

> What are we changing, and when?

It does not necessarily capture:

> What product capability must remain true over time?

As RAC grows, product intent needs to exist independently from release planning.

## Decision

Requirements shall represent long-lived product capabilities.

Roadmaps shall represent versioned delivery increments that satisfy, extend, or improve those requirements.

A requirement should not be tied to a specific release version.

For example:

```text
requirements/relationship-intelligence.md

implemented through:

roadmap/v0.7.0-explicit-relationships.md
roadmap/v0.7.1-repository-relationships.md
roadmap/v0.7.2-relationship-validation.md
```

The requirement survives beyond the original roadmap sequence.

Future releases may continue satisfying the same requirement.

## Principles

### Principle 1 — Requirements Describe Capabilities

Requirements should describe durable product behavior.

Examples:

```text
Good:

Relationship Intelligence
Repository Exploration
Artifact Quality
Markdown Source Format

Avoid:

v0.7 Relationship Requirements
v0.9 Explorer Requirements
```

Requirements should generally be named as product concepts rather than implementation changes.

## Principle 2 — Roadmaps Describe Change

Roadmaps should describe planned increments.

Examples:

```text
Good:

Add relationship validation
Introduce repository discovery
Implement Explorer navigation

Avoid:

Relationship Intelligence
Artifact Quality
```

Roadmaps should represent movement toward satisfying requirements.

## Principle 3 — Requirements Outlive Versions

A requirement may be delivered across many roadmap items.

Example:

```text
Requirement:
    Relationship Intelligence

Roadmaps:
    v0.7.0 Explicit Relationships
    v0.7.1 Repository Discovery
    v0.7.2 Relationship Validation
    v1.x Relationship Visualization
```

The requirement remains the canonical product intent.

## Principle 4 — Roadmaps Must Trace Back to Requirements

New roadmap items should reference the requirement they support.

Example:

```markdown
## Related Requirements

- requirements/relationship-intelligence.md
```

If a roadmap item has no related requirement, one of two things is likely true:

1. A missing requirement has been discovered.
2. The roadmap item may not represent meaningful product capability.

## Principle 5 — Artifact Relationships Form Product Knowledge

RAC repositories should form a connected knowledge graph.

The expected relationship model is:

```text
Requirement
    |
    ├── implemented by → Roadmap
    ├── constrained by → ADR
    ├── experienced through → Design
    └── delivered through → Implementation
```

No single artifact type should contain all product knowledge.

Each artifact should answer a different question.

## Rationale

Separating requirements from roadmaps improves:

- Product continuity
- Historical understanding
- Release planning
- Repository intelligence
- AI-assisted workflows

Without this separation, old roadmap files become the only explanation for why a capability exists.

With this separation:

- Requirements explain intent.
- Roadmaps explain delivery.
- ADRs explain decisions.
- Designs explain experiences.
- Prompts explain implementation guidance.

## Consequences

### Positive

- Clear separation between intent and delivery.
- Requirements remain stable across releases.
- Roadmap artifacts become smaller and more focused.
- Repository relationships become more meaningful.
- RAC can better analyze product knowledge health.

### Negative

- Additional artifact maintenance is required.
- Early-stage projects may feel like they have duplicate documentation.
- Contributors must understand artifact boundaries.

## Dogfooding Guidance

The RAC repository itself should follow this model.

Example structure:

```text
rac/
├── requirements/
│   ├── markdown-source-format.md
│   ├── artifact-validation.md
│   ├── artifact-improvement.md
│   ├── relationship-intelligence.md
│   ├── portfolio-intelligence.md
│   └── repository-exploration.md
│
├── roadmap/
├── adr/
├── design/
└── prompts/
```

Requirement artifacts should be created for existing capability areas and linked retrospectively to existing roadmap history.

## Alternatives Considered

### Roadmaps as Requirements

Use roadmap artifacts as the primary source of product intent.

#### Pros

- Fewer artifacts.
- Simpler early workflow.

#### Cons

- Couples intent to release timing.
- Makes historical reasoning harder.
- Encourages roadmap expansion without capability ownership.

### One Requirement per Release

Create requirement artifacts matching each version.

Example:

```text
requirements/v0.7.md
roadmap/v0.7.x
```

#### Pros

- Simple mapping.

#### Cons

- Requirements become release documentation.
- Long-lived product concepts become fragmented.

### Capability-Based Requirements (Selected)

Represent requirements as durable product capabilities.

#### Pros

- Stable product model.
- Better traceability.
- Better repository intelligence.
- Aligns with requirements-as-code principles.

## Success Measures

Evidence this decision is working:

- Every major roadmap stream traces to a requirement.
- Requirements change less frequently than roadmaps.
- New contributors can understand product intent without reading release history.
- RAC relationship analysis reveals connected artifact graphs.

## Review Date

Review before v1.0.0 once RAC has accumulated a larger requirements graph.
```