---
schema_version: 1
id: RAC-KTQ63DRET9QV
type: decision
---
# ADR-021: Templates as Artifact Creation Contracts

## Status

Accepted

## Context

RAC uses Markdown files as the canonical representation of product knowledge.

The repository contains multiple artifact types:

- Requirements
- Roadmaps
- ADRs
- Designs
- Prompts

Each artifact type has an expected structure that allows RAC to:

- Parse content consistently
- Validate completeness
- Detect relationships
- Provide improvement guidance
- Support repository intelligence

As RAC grows, users need a reliable way to create new artifacts without memorising expected formats.

Examples:

```bash
rac new requirement
rac new adr
rac new roadmap
```

Without a standard creation mechanism, artifact structure may drift between:

- Documentation examples
- User-created files
- Validation rules
- RAC's own dogfood repository

## Decision

RAC shall provide templates as the canonical artifact creation contracts.

Templates define the initial structure of artifacts created by RAC tooling.

Templates shall live with RAC source code and be distributed with the package.

Example:

```text
src/
└── rac/
    └── templates/
        ├── requirement.md
        ├── roadmap.md
        ├── adr.md
        ├── design.md
        └── prompt.md
```

Templates are not themselves product knowledge artifacts.

They are the mechanism used to create artifacts.

The RAC dogfood repository shall contain real artifacts only.

Example:

```text
rac/
├── requirements/
├── roadmap/
├── adr/
├── design/
└── prompts/
```

## Principles

### Principle 1 — Templates Create Artifacts

Templates define starting structure.

Example:

```text
Template
    ↓
creates
    ↓
Requirement Artifact
```

A template answers:

> What should a new artifact look like?

An artifact answers:

> What product knowledge exists?

These responsibilities should remain separate.

## Principle 2 — Templates Are Packaged Product Behavior

Templates are part of RAC itself.

They should:

- Version with the codebase
- Ship through package releases
- Be available offline
- Support CLI workflows

Users should not need to copy examples from documentation.

## Principle 3 — Templates Are Not Examples

Example artifacts demonstrate usage.

Templates define creation contracts.

Example:

```text
examples/
└── requirements/
    └── relationship-intelligence.md

src/rac/templates/
└── requirement.md
```

These serve different purposes.

## Principle 4 — Schemas Validate What Templates Produce

Templates and schemas should evolve together.

Expected lifecycle:

```text
Template
    ↓ creates

Artifact
    ↓ validated by

Schema
    ↓ interpreted by

RAC
```

A newly generated artifact should always pass baseline validation.

## Principle 5 — Dogfood Artifacts Remain Real

The RAC repository should not use placeholder templates as documentation.

Dogfood artifacts should represent genuine product knowledge.

For example:

```text
Good:

rac/requirements/repository-exploration.md

Avoid:

rac/templates/requirement-template.md
```

## Rationale

Templates provide a consistent entry point into requirements-as-code workflows.

They reduce:

- Formatting decisions
- Empty file creation
- Structural drift
- Onboarding friction

They improve:

- First user experience
- Validation reliability
- AI-assisted generation
- Repository consistency

## Consequences

### Positive

- Users can create valid artifacts quickly.
- RAC owns artifact creation standards.
- Templates, schemas, and validation can evolve together.
- Documentation does not become the source of truth.
- AI assistants have consistent artifact contracts.

### Negative

- Template changes become product changes.
- Template backwards compatibility must be considered.
- Additional packaging considerations are required.

## Relationship to Other ADRs

### ADR-001 — Markdown First

ADR-001 establishes Markdown as the canonical artifact format.

ADR-017 defines how new Markdown artifacts are created.

### ADR-016 — Requirements as Long-Lived Product Capabilities

ADR-016 defines artifact responsibility boundaries.

ADR-017 ensures new artifacts follow those boundaries from creation.

## Alternatives Considered

### Documentation-Only Templates

Maintain examples in documentation and require users to copy them.

#### Pros

- Simple implementation.
- No packaging concerns.

#### Cons

- Documentation becomes executable behaviour.
- Easy for examples and validation to drift.

### Dogfood Templates Directory

Store templates inside RAC's own artifact repository.

Example:

```text
rac/templates/
```

#### Pros

- Visible alongside artifacts.

#### Cons

- Mixes artifact instances with artifact definitions.
- Pollutes repository intelligence.
- Creates ambiguity during analysis.

### Packaged Templates (Selected)

Ship templates as part of RAC.

#### Pros

- Clear ownership.
- Version controlled.
- CLI accessible.
- Consistent with validation.

## Success Measures

Evidence this decision is working:

- New users can create artifacts without reading documentation first.
- Generated artifacts pass validation.
- Templates evolve alongside schemas.
- RAC dogfood repository contains only real product knowledge.
- Artifact structure remains consistent across repositories.

## Review Date

Review before v1.0.0 when artifact schemas and creation workflows stabilise.