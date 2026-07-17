---
schema_version: 1
id: RAC-KTR62H8G6YJJ
type: requirement
---
# REQ-Documentation-Structure

## Status

Accepted

## Problem

RAC requires a clear separation between:

- Public user-facing documentation
- Internal product knowledge artifacts
- Source code and tests

As RAC grows, there is a risk that the README becomes overloaded with:

- Full CLI documentation
- Artifact schemas
- ADR history
- Roadmaps
- Release notes
- Internal implementation details

This reduces discoverability and makes the project harder for new users to understand.

RAC should model its own philosophy:

- Knowledge should live in the correct artifact.
- Documentation should have clear ownership.
- Repository structure should communicate intent.

The documentation system should make RAC understandable within one minute while allowing deeper exploration through focused documents.

## Requirements

- [REQ-001] RAC shall organize project knowledge into three distinct documentation layers.
- [REQ-002] README.md shall serve as the project entry point.
- [REQ-003] docs/ shall serve as the user-facing documentation layer.
- [REQ-004] rac/ shall serve as the dogfooded requirements-as-code knowledge corpus.

## Goals

- Improve first-time user onboarding.
- Keep README concise and approachable.
- Keep documentation reviewed alongside code changes.
- Maintain separation between external documentation and internal planning artifacts.
- Demonstrate RAC repository conventions through dogfooding.

## Functional Requirements

### FR-001: README as Project Entry Point

README.md shall provide a concise introduction containing:

- What RAC is
- Who RAC is for
- Installation instructions
- Common CLI commands
- Minimal usage example
- Links to documentation
- Project status

README.md shall not attempt to document the full product.

Example sections:

```text
# Requirements as Code

## Install

## Quick Start

## Supported Artifact Types

## Documentation

## Project Status
```

## FR-002: User Documentation Directory

RAC shall maintain public documentation under:

```text
docs/
```

Documentation shall be organized by user task rather than implementation area.

Required documentation:

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

## FR-003: Quick Start Documentation

`docs/quickstart.md` shall answer:

> "How do I try RAC in five minutes?"

It should include:

- Installation
- Creating or locating an artifact
- Running validation
- Inspecting artifacts
- Understanding output

## FR-004: CLI Documentation

`docs/cli.md` shall answer:

> "What commands exist and what do they output?"

It should document:

- Command purpose
- Expected inputs
- Output formats
- Common examples

## FR-005: Artifact Documentation

`docs/artifacts.md` shall answer:

> "How should RAC artifacts be structured?"

It shall document supported artifact types:

- Requirements
- Decisions
- ADRs
- Roadmaps
- Prompts
- Designs

## FR-006: Relationship Documentation

`docs/relationships.md` shall answer:

> "How do IDs, references, and validation work?"

It should explain:

- Artifact relationships
- Reference metadata
- Validation failures
- Repository consistency checks

## FR-007: Repository Workflow Documentation

`docs/repo-workflow.md` shall describe the recommended RAC repository convention.

Example:

```text
rac/
  requirements/
  decision/
  roadmap/
  design/
  prompt/
```

It should demonstrate workflows such as:

```bash
rac stats rac/
rac validate rac/
rac relationships rac/ --validate
```

The goal is to position RAC as a way of organizing product knowledge in Git, not only as a CLI.

## FR-008: Testing Documentation

`docs/testing.md` shall document:

- Local development setup
- Running tests
- Expected verification workflow

This documentation must exist because testing instructions are required for contributors.

## FR-009: Changelog

The repository shall include:

```text
CHANGELOG.md
```

The changelog shall track meaningful user-visible changes between releases.

## Knowledge Artifact Requirements

RAC's own working knowledge shall remain under:

```text
rac/
```

Example:

```text
rac/
  adr/
  roadmap/
  prompt/
  design/
  decision/
```

This directory represents RAC's internal product corpus.

It shall contain:

- Architecture decisions
- Product decisions
- Roadmap artifacts
- Implementation prompts
- Design artifacts

It shall not replace user documentation.

## Repository Structure

The target repository structure shall be:

```text
README.md
CHANGELOG.md
CONTRIBUTING.md
LICENSE

docs/
  quickstart.md
  cli.md
  artifacts.md
  relationships.md
  repo-workflow.md
  testing.md
  examples.md

rac/
  adr/
  roadmap/
  prompt/
  design/
  decision/

src/
  rac/

tests/
```

## Non-Requirements

The following shall not be included in README.md:

- Complete CLI reference
- Full artifact schemas
- Complete roadmap history
- ADR archive
- Release process documentation
- Long examples
- Internal implementation notes

The project shall not use GitHub Wiki as the canonical documentation source.

Documentation should remain version controlled and reviewed through normal pull request workflows.

## Acceptance Criteria

- README.md can be read and understood in under one minute.
- Full product documentation exists outside README.md.
- Users can learn RAC without reading internal artifacts.
- Internal RAC artifacts remain available for dogfooding.
- Documentation changes can be reviewed alongside code changes.
- New contributors can run tests using repository documentation.

## Success Measures

- New users reach their first successful RAC command faster.
- README remains stable and concise.
- docs/ grows without increasing README complexity.
- rac/ continues representing real product knowledge.
- Contributors understand the difference between documentation and artifacts.

## Related Decisions

- ADR-018