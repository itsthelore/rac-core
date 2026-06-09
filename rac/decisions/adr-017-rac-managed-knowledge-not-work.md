---
schema_version: 1
id: RAC-KTQ63DQZ2VSV
type: decision
---
# ADR-017 — RAC Manages Knowledge, Not Work

## Status

Accepted

## Context

As RAC evolves beyond validation into inspection, repository analysis, and artifact relationships, there is a risk of gradually introducing project management concepts.

Many systems that begin as documentation or knowledge-management tools eventually expand to include:

* Ownership
* Assignment
* Prioritization
* Workflow states
* Scheduling
* Delivery tracking

These capabilities are commonly provided by tools such as Linear, Jira, Azure DevOps, and GitHub Projects.

RAC is intended to solve a different problem.

The purpose of RAC is to make requirements, decisions, roadmaps, prompts, and related artifacts machine-readable, inspectable, and traceable.

The purpose of RAC is not to coordinate work.

Without clear boundaries, future roadmap items could unintentionally introduce project management concerns and dilute the project's focus.

---

## Decision

RAC shall manage knowledge artifacts and their relationships.

RAC shall not manage work.

The project adopts the following principle:

> RAC manages knowledge.
>
> Git manages history.
>
> Other tools manage work.

Knowledge concerns include:

* Artifact structure
* Artifact validation
* Artifact classification
* Artifact relationships
* Artifact metadata
* Repository intelligence
* Traceability
* Decision rationale
* Historical context

Work-management concerns include:

* Ownership
* Assignment
* Prioritization
* Scheduling
* Sprint planning
* Delivery tracking
* Capacity management
* Workflow coordination

These concerns are explicitly outside the scope of RAC.

---

## Consequences

### Positive

RAC remains:

* Focused
* Lightweight
* Tool-agnostic
* Compatible with existing delivery workflows

Users may continue to use:

* GitHub Projects
* GitLab Issues
* Linear
* Jira
* Azure DevOps

alongside RAC without duplication of functionality.

The project maintains a clear separation between:

* Knowledge management
* Source control
* Work management

---

### Negative

Users seeking integrated planning and execution workflows will require additional tooling.

RAC will intentionally not answer questions such as:

* Who owns this requirement?
* When will this roadmap item be delivered?
* What sprint contains this work?
* What is the priority of this artifact?

Those concerns belong to dedicated project-management systems.

---

## Guidance

Artifact metadata should describe the artifact itself.

Examples:

```markdown
## Status

Superseded
```

```markdown
## Resolution

Delivered through v0.4.x
```

These are acceptable because they describe artifact history and context.

The following are not acceptable:

```markdown
## Owner

Tom
```

```markdown
## Sprint

Sprint 14
```

```markdown
## Due Date

2026-06-15
```

These fields describe work management rather than knowledge management.

Future roadmap proposals introducing ownership, scheduling, prioritization, workflow states, or resource allocation should be rejected unless this ADR is explicitly revisited.

---

## Alternatives Considered

### Introduce Lightweight Project Management

Allow roadmap artifacts to contain:

* Owners
* Priorities
* Delivery dates

Rejected.

This would create overlap with established project-management tools and increase the likelihood of RAC evolving into a competing planning system.

### Build a Complete Planning Layer

Extend RAC to support:

* Backlogs
* Workflow states
* Sprint management
* Task tracking

Rejected.

This is outside the purpose of Requirements-as-Code and would significantly increase complexity while reducing focus.

---

## Related Decisions

* ADR-002 — AI Optional
* ADR-013 — Git as System of Record
* ADR-014 — Viewer Agnostic
* ADR-015 — Repository Intelligence
* ADR-016 — Knowledge Graph Deferred
