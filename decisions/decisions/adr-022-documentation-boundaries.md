---
schema_version: 1
id: RAC-KTQ63DRJZPYN
type: decision
---
# ADR-022 Documentation Boundaries

## Status

Proposed

## Context

RAC treats product knowledge as structured, version-controlled artifacts.

Previous architectural decisions established:

- Markdown as the canonical artifact format.
- Git repositories as the source of truth.
- RAC's own repository as a dogfooded knowledge corpus.

As RAC grows, the project now contains multiple categories of information:

- User onboarding material
- CLI usage documentation
- Artifact specifications
- Repository workflow guidance
- Architecture decisions
- Roadmaps
- Design documents
- Implementation prompts

Without clear ownership boundaries, these categories risk becoming mixed together.

Common failure modes include:

- README.md becoming a large documentation dump.
- Internal roadmap and ADR content being presented as user documentation.
- User guides drifting away from source control.
- GitHub Wiki or external documentation becoming inconsistent with the repository.
- Contributors being unsure where new knowledge belongs.

RAC requires a documentation architecture that reflects its own principles:

- Knowledge should have an intentional location.
- Changes should be reviewed with code.
- Artifacts should remain focused.
- Repository structure should communicate meaning.

## Decision

RAC shall define three separate documentation layers:

```text
README.md
    ↓
Entry point

docs/
    ↓
User documentation

rac/
    ↓
Product knowledge artifacts
```

Each layer shall have a distinct responsibility.

## Documentation Layers

### Layer 1 — README.md

README.md shall act as the project front door.

Its purpose is to help a new user understand RAC quickly.

README.md should contain:

- Product summary
- Intended users
- Installation instructions
- Minimal usage examples
- Common commands
- Links to deeper documentation
- Project status

README.md shall not be treated as the complete product manual.

### Layer 2 — docs/

The docs directory shall contain user-facing documentation.

Examples:

```text
docs/
  quickstart.md
  cli.md
  artifacts.md
  relationships.md
  repo-workflow.md
  testing.md
  examples.md
```

Documentation should be organized around user goals.

Examples:

- "How do I start using RAC?"
- "What commands are available?"
- "How do I structure artifacts?"
- "How should a repository using RAC be organized?"

Documentation should not mirror implementation structure.

### Layer 3 — rac/

The rac directory shall contain RAC's own working knowledge corpus.

Examples:

```text
rac/
  adr/
  roadmap/
  requirement/
  design/
  prompt/
  decision/
```

This directory exists for:

- Architecture decisions
- Requirements
- Product planning
- Design exploration
- Implementation guidance

The rac directory demonstrates RAC usage but is not the primary onboarding path for users.

## Principles

### Principle 1 — README is a Doorway

README.md exists to create confidence quickly.

Users should understand:

- What RAC does.
- Why RAC exists.
- How to try it.

within approximately one minute.

Detailed explanations belong elsewhere.

### Principle 2 — Documentation Lives With Code

Canonical documentation shall remain inside the repository.

Documentation changes should happen through the same workflow as:

- Code changes
- Tests
- Artifact updates

This ensures documentation evolves alongside the product.

### Principle 3 — Avoid GitHub Wiki as Source of Truth

GitHub Wiki shall not contain canonical RAC documentation.

External documentation systems may exist in the future, but repository Markdown remains authoritative.

### Principle 4 — Artifacts Are Not Documentation Pages

RAC artifacts are structured product knowledge.

They are designed for:

- Traceability
- Validation
- Historical reasoning
- Automation

They should not replace task-based user guides.

### Principle 5 — Dogfood Without Exposing Complexity

RAC should demonstrate its own usage through rac/.

However, users should not need to understand RAC's internal:

- ADR history
- Roadmap planning
- Design discussions
- Implementation prompts

before becoming productive.

## Consequences

### Positive

- README remains concise.
- New users onboard faster.
- Documentation ownership becomes clearer.
- Repository navigation improves.
- RAC demonstrates its own artifact model.
- Documentation changes are reviewed with product changes.
- Future tooling can reason about documentation structure.

### Negative

- More files must be maintained.
- Contributors need to understand documentation boundaries.
- Some information may require cross-linking between layers.

## Alternatives Considered

### Single README Documentation Model

Keep all documentation in README.md.

#### Pros

- Simple repository structure.
- Everything is immediately visible.

#### Cons

- README grows indefinitely.
- Harder to navigate.
- Poor separation of concerns.
- Encourages unrelated documentation changes.

Rejected.

---

### GitHub Wiki Documentation

Move detailed documentation into GitHub Wiki.

#### Pros

- Keeps repository smaller.
- Provides separate documentation area.

#### Cons

- Documentation changes are not reviewed with code.
- Documentation can drift.
- Less compatible with RAC validation.
- Removes documentation from Git workflows.

Rejected.

---

### RAC Artifacts as User Documentation

Expose rac/ as the primary documentation system.

#### Pros

- Maximum dogfooding.
- Demonstrates RAC concepts.

#### Cons

- Confuses internal knowledge with user guidance.
- Requires users to understand RAC before learning RAC.
- Creates onboarding friction.

Rejected.

---

### Three-Layer Documentation Model

Separate:

```text
README.md → introduction
docs/     → user knowledge
rac/      → product knowledge
```

#### Pros

- Clear ownership.
- Strong onboarding path.
- Supports dogfooding.
- Keeps knowledge version controlled.
- Aligns with RAC philosophy.

#### Cons

- Requires maintaining clear boundaries.

Accepted.

## Relationship to Other Artifacts

### Related Requirements

- REQ-Documentation-Structure

Defines the required repository documentation layout and expected user-facing documentation.

### Related ADRs

- ADR-001 Markdown First

Documentation and artifacts remain Markdown-native.

- ADR-013 Leverage Existing Source Control Systems

Documentation remains part of the repository workflow.

- ADR-018 RAC Directory as Dogfooded Knowledge Corpus

Defines rac/ as the home of RAC's internal structured artifacts.

## Success Measures

Evidence that this decision is working:

- README remains short and stable.
- Users can understand RAC without reading rac/.
- docs/ contains complete user guidance.
- rac/ continues evolving as structured product knowledge.
- Documentation updates appear alongside relevant code changes.
- Repository contributors understand where new information belongs.

## Review Date

Review before v1.0.0 or when introducing external documentation hosting.