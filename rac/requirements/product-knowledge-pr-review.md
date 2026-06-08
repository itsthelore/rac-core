# Requirement: Product Knowledge Pull Request Review

## Status

Proposed

## Context

RAC enables Markdown product artifacts to be inspected, validated, compared, and connected.

Existing capabilities include:

- artifact validation
- structural analysis
- artifact diffing
- relationship validation
- repository statistics
- improvement guidance

However, these capabilities currently depend on users intentionally running CLI commands.

Modern engineering workflows already have a natural quality gate:

Pull Requests.

Code changes are automatically checked before merge through:

- tests
- linting
- formatting
- security checks
- dependency checks

Product knowledge should receive the same treatment.

RAC should make product specifications reviewable, testable, and safe to change before engineering work begins.

## Requirement

RAC shall provide a Git-native review workflow that automatically validates product knowledge changes during pull requests.

A team should be able to install RAC once and have product artifact quality checked continuously.

## Product Goal

Move RAC from:

> A CLI toolkit for Markdown product artifacts.

toward:

> The default PR check for product specifications before engineering starts.

## User Workflow

A user should be able to configure RAC through:

```bash
rac init
```

which creates:

```text
rac/
  requirements/
  decisions/
  roadmaps/
  designs/
  prompts/

.github/
  workflows/
    rac.yml
```

After setup, product documentation changes should automatically trigger RAC checks during pull requests.

## Functional Requirements

## GitHub Action Integration

RAC shall provide a standard GitHub Actions workflow.

The workflow shall support:

- repository checkout
- RAC installation
- artifact validation
- relationship validation
- repository review checks

Example:

```yaml
rac validate rac/
rac relationships rac/ --validate
rac review rac/
```

## Pull Request Review Summary

RAC shall provide human-readable PR feedback.

Examples:

```text
RAC Review

3 Requirements changed
2 Decisions updated
1 Roadmap added

Issues:

❌ Requirement AUTH-002 missing Success Measures

❌ Decision ADR-004 references missing ADR-001

⚠️ Roadmap Q3 valid but missing Metrics
```

## Product Knowledge Diff

RAC shall summarize artifact changes between commits.

Examples:

```text
This PR:

Added:
+ 4 Requirements

Modified:
~ 2 Decisions

Removed:
- 1 Design

Relationship impact:
- 1 broken reference introduced
```

## Configurable Quality Gates

Teams shall control which issues block merges.

Examples:

Required:

- invalid artifact structure
- broken relationships
- duplicate identifiers

Optional warnings:

- missing recommended sections
- improvement suggestions
- portfolio health changes

Example configuration:

```yaml
fail_on:
  - invalid_artifact
  - broken_relationship
  - duplicate_id

warn_on:
  - missing_recommended_section
```

## Machine Readable Output

All PR functionality must consume existing RAC outputs.

Required:

```bash
rac review rac/ --json
```

The GitHub integration must not contain independent analysis logic.

## Non-Goals

RAC PR Review shall not:

- replace human product review
- approve requirements automatically
- rewrite artifacts
- require GitHub as the storage layer
- introduce a hosted service dependency
- duplicate RAC core logic

## Architecture Requirements

The implementation order shall remain:

```text
Core RAC capability
        ↓
CLI command
        ↓
JSON contract
        ↓
GitHub integration
        ↓
Future consumers
```

GitHub Actions are consumers of RAC intelligence.

They are not the source of RAC intelligence.

## Acceptance Criteria

A new user can:

1. Install RAC

```bash
uv tool install requirements-as-code
```

2. Initialize a repository

```bash
rac init
```

3. Open a pull request changing product docs

4. Automatically receive:

- artifact validation results
- relationship validation results
- repository review summary
- product knowledge diff

without manually running RAC.

## Success Measures

This requirement succeeds when:

- RAC becomes part of normal PR workflows.
- Product docs receive automated checks like source code.
- Teams catch requirement problems before implementation.
- AI-generated product changes can be verified deterministically.
- Product knowledge changes become safe to review and merge.

## Related Artifacts

- Requirement: Repository Review Mode
- ADR: Markdown First
- ADR: Repository Intelligence as the Value Layer
- ADR: Explorer as a Consumer

## Future Considerations

Future versions may support:

- additional CI providers
- branch comparison reports
- organization-specific policies
- required approval rules
- MCP integration for agent-generated PRs
- richer Explorer visualization

These should extend the same review contract rather than introduce separate workflows.