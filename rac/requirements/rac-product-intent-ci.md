# Requirement: Product Intent CI

## Status

Proposed

## Context

Software engineering workflows protect code changes using:

- automated tests
- static analysis
- linting
- CI checks
- ownership rules

Product knowledge rarely receives equivalent protection.

Requirements, roadmaps, decisions, and design documents often change without automated verification.

This risk increases as AI agents begin generating and modifying product artifacts.

RAC should provide continuous verification of product intent before changes are merged.

## Requirement

RAC shall provide CI-native product knowledge validation that automatically reviews product artifact changes during pull requests.

Product intent changes should become testable, reviewable, and safe to merge.

## Product Goal

Move RAC from:

> A CLI toolkit for product documents.

toward:

> CI for product intent.

## User Story

As a team using Git-based product artifacts,

when a pull request changes requirements or decisions,

I want automated RAC checks,

so that invalid, ambiguous, or disconnected product changes are caught before merge.

## Interfaces

### CLI

Required:

```bash
rac guard
```

Optional:

```bash
rac guard --base main --head HEAD
rac guard --format json
rac guard --format github
```

### GitHub Actions

RAC shall provide a standard workflow.

Example:

```yaml
name: RAC Product Intent Check

steps:
  - run: rac guard
```

## Functional Requirements

## Pull Request Safety Gate

RAC shall analyze product artifact changes before merge.

Checks include:

- artifact validity
- relationship integrity
- missing required information
- unsafe product changes

Example:

```text
RAC Guard

Status:
Review Required

Issues:

- 2 invalid Requirements
- 1 broken Decision reference
```

## GitHub Review Output

RAC shall provide PR-native feedback.

Including:

- changed artifacts
- introduced issues
- removed information
- recommended review actions

Example:

```text
Product Intent Summary

Added:
+ 3 Requirements

Changed:
~ 1 Decision

Issues:
- Requirement removed acceptance criteria
- Roadmap references missing requirement
```

## GitHub Check Annotations

RAC should support inline review feedback.

Example:

```text
"quickly"

Issue:
Ambiguous requirement language introduced.

Recommendation:
Replace with measurable criteria.
```

## Configurable Merge Gates

Teams shall configure which findings block merges.

Example:

```yaml
fail_on:
  - invalid_artifact
  - broken_relationship

warn_on:
  - missing_recommended_section
```

## Product Ownership Rules

RAC should support ownership policies for product knowledge.

Example:

```yaml
ownership:
  requirements/billing/*:
    reviewers:
      - billing-owner
```

Changes affecting owned product areas may require review.

## Product Change Summary

RAC shall summarize intent changes.

Example:

```text
This PR:

Added:
- 4 Requirements

Modified:
- Checkout success metric

Removed:
- Legacy billing constraint
```

## JSON Contract

All CI functionality shall consume structured RAC output.

Required consumers:

- GitHub Actions
- AI agents
- MCP
- future integrations

## Non-Goals

Product Intent CI shall not:

- decide product correctness
- replace product owners
- rewrite artifacts automatically
- depend exclusively on GitHub
- duplicate RAC analysis logic

## Architecture Requirements

Implementation flow:

```text
RAC Core Intelligence
          |
          |
    rac guard
          |
          |
 JSON / GitHub Output
          |
          |
 CI Providers / Agents
```

CI integrations are consumers.

They are not the source of product intelligence.

## Acceptance Criteria

A team can:

1. Install RAC.
2. Add RAC to CI.
3. Open a product artifact pull request.
4. Receive automated product intent feedback.
5. Block unsafe changes before merge.

## Success Measures

RAC succeeds when:

- product changes receive automated review like code changes
- AI-generated requirement edits become safer
- teams catch broken intent before engineering starts
- product documentation becomes continuously verified

## Related Artifacts

- Requirement: Repository Review Mode
- Requirement: AI Spec Safety Review
- ADR: Markdown First
- ADR: Repository Intelligence as the Value Layer
- ADR: Explorer as a Consumer

## Future Considerations

Future capabilities may include:

- additional CI providers
- advanced ownership workflows
- product impact graphs
- release intent summaries
- historical product drift detection
```