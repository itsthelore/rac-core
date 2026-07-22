# Design: Explorer Recommendations

## Status

Proposed

## Purpose

Define how repository recommendations are presented within Explorer.

Recommendations help users improve repository quality and maintainability.

## Design Principles

### Explain Before Suggesting

Users should understand:

- what is wrong
- why it matters
- what action is recommended

### Prioritise Attention

Not all findings have equal importance.

Explorer should help users identify high-value actions.

### Recommendations Are Advisory

Recommendations do not automatically modify content.

Human judgement remains responsible for repository decisions.

## Recommendation Categories

### Validation

Examples:

- Missing required sections
- Invalid metadata

### Relationships

Examples:

- Broken references
- Missing links

### Repository Health

Examples:

- Orphaned artifacts
- Low traceability

### Quality

Examples:

- Missing success measures
- Weak acceptance criteria

## Presentation

Recommendations should include:

### Finding

Description of the issue.

### Impact

Why the issue matters.

### Suggested Action

Recommended remediation.

### Navigation

Direct access to affected artifacts. Selecting a recommendation opens the
artifact on its Findings tab, where the same finding is shown in the
artifact's own context (v0.8.9).

### Improvement Suggestions

For artifact types the improve service supports, the artifact's Findings
tab also carries an Improvement group sourced from `rac improve`: one row
per missing section, with the schema's guidance question as the suggested
action (v0.8.9). Improvements are fetched when an artifact opens — never
during repository load — and follow the same render-only rule as every
recommendation.

## Severity Levels

Initial severity model:

- Critical
- Warning
- Suggestion

Severity definitions are maintained separately by repository intelligence services.

## Non-Goals

Recommendations shall not:

- automatically apply changes
- rewrite artifacts
- replace human review

## Related Artifacts

- Requirement: Product Knowledge Navigator (Explorer)
- DESIGN-health-model
- DESIGN-action-workflows