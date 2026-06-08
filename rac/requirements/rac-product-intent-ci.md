# Requirement: Product Intent CI

## Status

Proposed

## Context

Software engineering workflows protect code changes through automated review systems:

- tests
- linting
- formatting
- static analysis
- CI checks

Product knowledge rarely receives the same level of visibility.

Requirements, decisions, roadmaps, designs, and prompts often change without reviewers understanding:

- what product intent changed
- what relationships were affected
- whether documentation remains valid
- whether important context was removed

This risk increases as AI agents begin contributing directly to product artifacts.

RAC already provides deterministic product knowledge intelligence through:

- artifact inspection
- validation
- diffing
- repository statistics
- schema analysis
- improvement guidance
- relationship validation

The next step is surfacing that intelligence where teams already review change:

Pull Requests.

## Requirement

RAC shall provide a Git-native product knowledge review layer called:

**RAC Watchkeeper**

Watchkeeper shall observe product artifact changes and surface RAC intelligence during pull request workflows.

## Product Goal

Move RAC from:

> A CLI toolkit users manually execute.

toward:

> Continuous review for product intent changes.

## Product Model

RAC provides multiple surfaces over the same intelligence:

```text
RAC Core
    |
    +-- Explorer
    |     Navigate product knowledge
    |
    +-- Watchkeeper
          Review product knowledge changes
```

Explorer helps users understand existing knowledge.

Watchkeeper helps users understand changing knowledge.

## User Story

As a team storing product knowledge in Git,

when humans or AI agents modify requirements, decisions, or roadmaps,

I want RAC to review those changes automatically,

so that reviewers understand product impact before merge.

## Dependency

Watchkeeper consumes existing RAC capabilities:

- Repository Review Mode
- Artifact validation
- Artifact diffing
- Relationship validation
- Repository statistics
- Improvement suggestions
- AI Spec Safety checks

Watchkeeper shall not implement independent analysis logic.

## User Workflow

A user installs RAC:

```bash
uv tool install requirements-as-code
```

Then initializes repository workflows:

```bash
rac init
```

RAC creates:

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

Pull requests automatically receive Watchkeeper reviews.

## Interface

Required:

```bash
rac watchkeeper
```

Optional:

```bash
rac watchkeeper --base main --head HEAD

rac watchkeeper --format json

rac watchkeeper --format github
```

Internally:

```text
Watchkeeper
      |
      +-- Review Mode
      |
      +-- Diff Analysis
      |
      +-- Relationship Checks
      |
      +-- Safety Analysis
```

## Functional Requirements

## Pull Request Review Summary

Watchkeeper shall publish a product knowledge summary.

Example:

```text
RAC Watchkeeper

Product knowledge changes detected.

Changed:

+ 3 Requirements
~ 1 Decision
~ 1 Roadmap

Validation:

✓ All artifacts valid

Relationships:

⚠ REQ-004 references missing ADR-002

Suggestions:

Add Success Measures section.
```

## Changed Artifact Detection

Watchkeeper shall identify:

- added artifacts
- modified artifacts
- removed artifacts
- artifact type changes

Example:

```text
Changed:

Added:
+ requirements/billing-upgrade.md

Modified:
~ decisions/payment-provider.md
```

## Relationship Change Reporting

Watchkeeper shall identify relationship impact.

Including:

- new relationships
- removed relationships
- broken references
- ambiguous references

Example:

```text
Relationship Impact:

REQ-010 modified.

Affected:

- ROADMAP-Q3
- ADR-004
```

## Repository Statistics Delta

Watchkeeper shall summarize repository-level changes.

Example:

```text
Repository Changes:

Requirements:
42 → 45

Decisions:
12 → 13

Invalid artifacts:
0 → 1
```

## Review Recommendations

Watchkeeper shall recommend human review when needed.

Example:

```text
Review recommended:

Reason:
Acceptance criteria removed from Requirement.
```

Watchkeeper does not determine whether a product decision is correct.

It identifies changes requiring attention.

## Configurable Review Policies

Teams shall configure review behavior.

Example:

```yaml
watchkeeper:
  require_review:
    - broken_relationship
    - acceptance_criteria_removed

  warn_on:
    - missing_recommended_section
```

Policies determine workflow behavior.

The underlying RAC analysis remains unchanged.

## GitHub Integration

Watchkeeper shall support GitHub-native output.

Including:

- pull request comments
- check summaries
- inline annotations where appropriate

Users should not need to run RAC locally to understand product artifact changes.

## Machine Readable Contract

Watchkeeper shall expose structured output:

```bash
rac watchkeeper --format json
```

Consumers include:

- GitHub Actions
- CI systems
- MCP servers
- AI agents
- Explorer

## Non-Goals

Watchkeeper shall not:

- replace product reviewers
- approve product decisions automatically
- rewrite requirements
- require GitHub specifically
- require hosted infrastructure
- duplicate RAC core logic

## Architecture Requirements

Implementation order:

```text
RAC Intelligence
        |
        |
 Repository Review
        |
        |
 Watchkeeper
        |
        |
 GitHub / CI / Agents
```

Watchkeeper is a consumer of RAC intelligence.

It is not a separate intelligence engine.

## Acceptance Criteria

A team can:

1. Initialize RAC.
2. Open a pull request changing product artifacts.
3. Receive a Watchkeeper report containing:
   - changed artifacts
   - validation status
   - relationship impact
   - repository changes
   - review recommendations

without manually running RAC commands.

## Success Measures

Watchkeeper succeeds when:

- product knowledge changes become visible during review
- reviewers understand intent changes before merge
- AI-generated artifact changes become easier to verify
- RAC becomes part of normal engineering workflows
- product artifacts receive the same review discipline as code

## Related Artifacts

- Requirement: Repository Review Mode
- Requirement: AI Spec Safety
- ADR: Markdown First
- ADR: Repository Intelligence as the Value Layer
- ADR: Explorer as a Consumer

## Future Considerations

Future versions may add:

- additional CI providers
- ownership workflows
- approval policies
- release intent summaries
- historical drift reports
- advanced agent integrations
```