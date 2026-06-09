---
schema_version: 1
id: RAC-KTQ63DR3G4YG
type: decision
---
# ADR-018: RAC Directory as the Canonical Knowledge Root

## Status

Accepted

## Context

RAC treats structured product knowledge as a first-class part of a repository.

Requirements, decisions, roadmaps, designs, prompts, and future artifact types are not traditional documentation. They represent the intent layer of a system:

- why something exists
- what decisions shaped it
- what should happen next
- how different pieces of knowledge relate

Early RAC development stored these artifacts under:

```text
planning/
```

This worked during initial development but increasingly misrepresented the purpose of the artifacts.

The term "planning" implies:

- future work only
- project management activity
- temporary documents
- implementation tracking

RAC artifacts are broader than planning. They describe persistent product and engineering knowledge that remains valuable before, during, and after implementation.

As RAC begins dogfooding its own conventions and introducing richer repository experiences such as Explorer, a clearer canonical structure is required.

## Decision

RAC shall adopt:

```text
rac/
```

as the conventional root directory for RAC artifacts.

Example:

```text
rac/
├── requirements/
├── decisions/
├── roadmaps/
├── designs/
└── prompts/
```

The `rac/` directory represents the repository's structured knowledge layer.

It contains human-authored artifacts that describe product intent, architectural reasoning, delivery plans, design thinking, and AI collaboration context.

## Principles

### Principle 1 — RAC Contains Knowledge, Not Documentation

The `rac/` directory is not a documentation folder.

Documentation explains what exists.

RAC artifacts explain:

- what should exist
- why it exists
- how decisions were made
- how concepts relate

The distinction is intentional.

### Principle 2 — Convention Over Configuration

`rac/` shall become the recommended default location created by RAC tooling.

For example:

```bash
rac init
```

may generate:

```text
.rac/
└── config.toml

rac/
├── requirements/
├── decisions/
├── roadmaps/
├── designs/
└── prompts/
```

This provides a predictable structure for:

- humans
- automation
- AI systems
- future RAC consumers

### Principle 3 — The Directory Is Conventional, Not Mandatory

RAC remains repository-native and path-agnostic.

Users may continue to run RAC against any directory:

```bash
rac inspect ./docs
rac inspect ./product
rac inspect ./planning
```

The existence of a recommended convention must not create a hard dependency.

`rac/` is the golden path, not a requirement.

### Principle 4 — Configuration and Knowledge Remain Separate

Future RAC configuration or machine-managed state should not be stored alongside human-authored artifacts.

The intended separation is:

```text
.rac/
    tool configuration

rac/
    product knowledge artifacts
```

This mirrors existing repository conventions where hidden directories contain tooling configuration while visible directories contain user-owned content.

### Principle 5 — Consumers Should Discover RAC Knowledge

RAC consumers such as Explorer should treat `rac/` as the default discovery location.

Examples:

- CLI workflows
- Terminal interfaces
- IDE integrations
- AI assistants
- future visualization tools

However, consumers should support explicitly supplied paths and avoid assuming all repositories follow the convention.

## Rationale

Naming influences how users understand a system.

A repository containing:

```text
planning/
```

suggests project plans.

A repository containing:

```text
rac/
```

suggests a dedicated knowledge layer.

This better aligns with RAC's long-term purpose:

```text
source code
    +
structured intent
    =
understandable systems
```

The directory itself becomes part of the product model.

## Consequences

### Positive

- Creates a recognizable RAC repository convention.
- Improves dogfooding alignment.
- Makes examples and onboarding clearer.
- Provides a natural default for `rac init`.
- Strengthens the distinction between RAC artifacts and documentation.
- Makes future Explorer behavior simpler.

### Negative

- Existing repositories using `planning/` may need migration.
- New users may initially need to learn what the `rac/` folder represents.
- Tooling must avoid incorrectly assuming only one valid location.

## Migration

Existing RAC repositories may migrate from:

```text
planning/
```

to:

```text
rac/
```

No artifact format changes are required.

This is a structural convention change only.

## Alternatives Considered

### Keep `planning/`

Continue storing artifacts under the existing directory.

#### Pros

- No migration required.
- Familiar terminology.

#### Cons

- Too narrow.
- Suggests temporary planning documents.
- Does not represent decisions, prompts, designs, or future artifact types.

### Use `docs/`

Store RAC artifacts alongside documentation.

#### Pros

- Familiar repository convention.
- Easy for users to discover.

#### Cons

- Blurs the distinction between documentation and structured knowledge.
- Encourages treating RAC artifacts as static text.

### Use `product/`

Create a product-focused knowledge directory.

#### Pros

- Clear for product teams.
- Strong association with requirements and roadmaps.

#### Cons

- Less applicable to engineering decisions, AI workflows, and broader system knowledge.

### Use `knowledge/`

Create a generic knowledge repository.

#### Pros

- Accurately describes the concept.

#### Cons

- Less distinctive.
- More similar to traditional knowledge bases or wikis.

## Relationship to Other ADRs

### ADR-012 — Repository Intelligence as the Value Layer

ADR-012 establishes RAC's ability to understand repositories.

ADR-016 establishes where RAC-native repositories conventionally store that knowledge.

### ADR-014 — Viewer-Agnostic Knowledge Artifacts

ADR-014 ensures artifacts remain independent of any viewer.

ADR-016 defines a default location without introducing viewer coupling.

### ADR-015 — Explorer as a Consumer

ADR-015 establishes Explorer as a consumer of RAC capabilities.

ADR-016 gives Explorer a sensible default discovery convention while preserving path independence.

## Success Measures

Evidence this decision is successful:

- New RAC repositories naturally adopt `rac/`.
- Documentation examples consistently use the convention.
- Explorer can provide a first-run experience without configuration.
- Existing path-based workflows continue working.
- Users describe RAC artifacts as repository knowledge rather than project documents.

## Review Date

Review at v1.0.0 once external adoption patterns are better understood.
```