---
schema_version: 1
id: RAC-KTR62H8P3P1S
type: requirement
---
# Requirement: Product Intent CI (Watchkeeper)

## Status

Proposed

## Problem

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
- whether artifacts remain valid
- whether important context was removed
- whether requirements became less precise

This risk increases as AI agents become active contributors to product documentation.

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

## Requirements

- [REQ-001] RAC shall provide a Git-native product knowledge review layer called RAC Watchkeeper.

- [REQ-002] Watchkeeper shall observe product artifact changes and surface RAC intelligence during pull request workflows.

- [REQ-003] Watchkeeper shall help reviewers answer: what changed, and does this product intent need attention?

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

when humans or AI agents modify requirements, decisions, roadmaps, designs, or prompts,

I want RAC to review those changes automatically,

so that reviewers understand product impact before merge.

## Dependency

Watchkeeper consumes existing RAC capabilities:

- Repository Review Mode
- Artifact validation
- Artifact inspection
- Artifact diffing
- Relationship validation
- Repository statistics
- Schema suggestions
- Improvement suggestions

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
      +-- Repository Review
      |
      +-- Artifact Diff
      |
      +-- Relationship Checks
      |
      +-- Intent Safety Checks
```

## Functional Requirements

## Pull Request Review Summary

Watchkeeper shall publish a product knowledge review.

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
Added:

+ requirements/billing-upgrade.md

Modified:

~ decisions/payment-provider.md
```

## Product Knowledge Diff

Watchkeeper shall summarize meaningful artifact changes.

Examples:

- requirements added
- decisions changed
- acceptance criteria modified
- constraints removed
- success measures changed

The output should describe product impact rather than raw Markdown differences.

Example:

```text
Requirement changed:

REQ-004 Checkout Performance

Previous:
Payment confirmation within 2 seconds.

Current:
Payment confirmation should happen quickly.

Finding:
Specific measurable criteria removed.
```

## Intent Safety Checks

Watchkeeper shall detect changes that reduce product clarity.

These checks apply regardless of whether the change was created by:

- a human
- an AI agent
- an automation

The concern is the change itself, not authorship.

## Specificity Regression Detection

Watchkeeper shall identify when precise requirements become vague.

Example:

```diff
- Upload must complete within 5 seconds.
+ Upload should complete quickly.
```

Finding:

```text
Specificity regression detected.

A measurable requirement was replaced with ambiguous wording.
```

## Ambiguity Detection

Watchkeeper shall identify unclear product language without measurable criteria.

Examples:

- fast
- easy
- simple
- seamless
- intuitive
- user-friendly
- scalable

Example:

```text
Issue:

"Checkout should be seamless."

Reason:

No measurable success criteria provided.
```

## Constraint Change Detection

Watchkeeper shall detect removed or weakened constraints.

Examples:

- acceptance criteria removed
- success metrics removed
- requirements weakened
- mandatory language changed

Example:

```diff
- System must support WCAG 2.2 AA.
+ System should be accessible.
```

## Unlinked Scope Detection

Watchkeeper shall identify new product scope without supporting context.

Examples:

- new requirement without roadmap relationship
- new dependency without decision record
- new design behavior without linked requirement

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

Watchkeeper shall recommend human attention when needed.

Example:

```text
Review recommended.

Reasons:

- Acceptance criteria removed
- New requirement introduced without linked decision
```

Watchkeeper does not determine whether a product decision is correct.

It identifies changes requiring review.

## Configurable Review Policies

Teams shall configure review behavior.

Example:

```yaml
watchkeeper:
  require_review:
    - broken_relationship
    - acceptance_criteria_removed
    - specificity_regression

  warn_on:
    - missing_recommended_section
    - ambiguity_introduced
```

Policies determine workflow behavior.

The underlying RAC analysis remains deterministic.

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
- determine whether content was AI-generated
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
- statistics changes
- intent safety findings
- review recommendations

without manually running RAC commands.

## Success Measures

Watchkeeper succeeds when:

- product knowledge changes become visible during review
- reviewers understand intent changes before merge
- AI-generated artifact changes become safer
- RAC becomes part of normal engineering workflows
- product artifacts receive the same review discipline as code

## Related Artifacts

- Requirement: Repository Review Mode
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