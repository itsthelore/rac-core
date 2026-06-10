---
schema_version: 1
id: RAC-KTR62H8XA5D4
type: requirement
---
# Requirement: Repository Review Mode

## Status

Proposed

## Problem

RAC provides deterministic analysis of product knowledge stored as Markdown artifacts.

Existing capabilities include:

- artifact inspection
- artifact validation
- artifact classification
- schema enforcement
- relationship analysis
- repository statistics
- improvement guidance

However, these capabilities currently exist as separate commands.

Users must know which RAC primitive to execute and manually combine the results to understand repository health.

As RAC evolves into infrastructure for product knowledge, users and automation systems need a single entry point that answers:

> What needs attention in this repository?

## Requirements

- [REQ-001] RAC shall provide a repository-level review workflow that aggregates product knowledge analysis into a single actionable report.

- [REQ-002] Review Mode shall become the primary interface for understanding the state of a RAC repository.

## Product Goal

Move RAC from:

> Individual commands that analyze product artifacts.

toward:

> A repository intelligence layer that explains product knowledge health.

## User Story

As a product owner, engineer, or AI agent,

when reviewing a repository of product artifacts,

I want one command that summarizes quality, completeness, and relationship health,

so that I know what requires attention before work continues.

## Interface

Users shall run:

```bash
rac review <path>
```

Machine consumers shall run:

```bash
rac review <path> --json
```

## Functional Requirements

### Artifact Discovery

Review Mode shall summarize discovered artifacts.

Including:

- Requirements
- Decisions
- Roadmaps
- Designs
- Prompts
- Unknown artifacts

Example:

```text
Artifacts:

Requirements: 12
Decisions: 8
Roadmaps: 4
Unknown: 2
```

## Validation Summary

Review Mode shall aggregate validation results.

Including:

- invalid artifact structures
- missing required sections
- schema violations

Example:

```text
Issues:

REQ-004 invalid:
Missing Acceptance Criteria section
```

## Relationship Summary

Review Mode shall report relationship health.

Including:

- broken references
- ambiguous references
- duplicate identifiers
- self-references
- disconnected artifacts

Example:

```text
ADR-006 references ADR-002.

Issue:
ADR-002 does not exist.
```

## Repository Health Summary

Review Mode shall prioritize issues by impact.

Priority order:

1. Invalid artifacts
2. Broken relationships
3. Missing required information
4. Missing recommended information
5. Improvement suggestions

## Suggested Actions

Review Mode shall recommend deterministic next steps.

Example:

```text
Suggested action:

Run:
rac schema requirement --template
```

or:

```text
Add missing Success Measures section.
```

## JSON Contract

Structured output shall include:

- artifact inventory
- validation results
- relationship results
- issue severity
- suggested actions

The JSON contract shall support:

- GitHub Actions
- CI workflows
- MCP integrations
- AI agents
- Explorer

## Non-Goals

Review Mode shall not:

- rewrite artifacts automatically
- replace human review
- generate product decisions
- duplicate existing RAC command logic
- contain UI-specific behavior

## Architecture Requirements

Review intelligence shall exist in the RAC service layer.

Consumers shall follow:

```text
Core RAC Review Engine
          |
          |
     CLI / JSON
          |
          |
 GitHub / MCP / Explorer
```

Explorer and integrations consume Review Mode.

They do not implement review logic.

## Acceptance Criteria

- A repository can be reviewed using one command.
- Review combines existing RAC intelligence.
- JSON output provides a stable automation contract.
- Existing commands remain available independently.
- Future integrations consume the same review results.

## Related Artifacts

- ADR: Markdown First
- ADR: Repository Intelligence as the Value Layer
- ADR: Explorer as a Consumer

## Future Considerations

Future versions may add:

- repository scoring
- historical trends
- configurable policies
- organization-specific rules
```