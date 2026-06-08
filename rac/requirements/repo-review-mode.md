# Requirement: Repository Review Mode

## Status

Proposed

## Context

RAC provides deterministic analysis primitives for product knowledge repositories.

Existing capabilities include:

- Artifact inspection
- Artifact validation
- Repository statistics
- Relationship analysis
- Artifact improvement guidance
- Schema and template discovery

These capabilities expose valuable repository intelligence, but users must currently know which individual command to run and how to combine the results.

As RAC expands beyond individual artifact checks, users need a single workflow that answers:

> What needs attention in this product knowledge repository?

Review Mode provides a unified repository health workflow while preserving RAC's core principles:

- Markdown remains the source of truth.
- Intelligence remains deterministic.
- CLI workflows remain first-class.
- Explorer and future integrations consume RAC capabilities rather than owning them.

## Requirement

RAC shall provide a repository-level review capability that aggregates existing analysis primitives into a single actionable workflow.

Users shall be able to run:

```bash
rac review <path>
```

and receive a prioritized summary of repository health, including:

- discovered artifacts
- artifact classifications
- validation results
- relationship issues
- structural completeness
- recommended next actions

## Goals

### Provide a Single Review Entry Point

Users should not need to manually combine multiple commands to understand repository state.

Review Mode should answer:

- What artifacts exist?
- Which artifacts are healthy?
- Which artifacts need attention?
- What should be fixed first?

### Aggregate Existing RAC Intelligence

Review Mode should reuse existing capabilities including:

- inspection
- validation
- relationships
- statistics
- improvement signals

Review Mode must not create duplicate implementations of existing analysis logic.

### Support Human and Machine Consumers

Review results shall be available through:

```bash
rac review <path>
```

for humans and:

```bash
rac review <path> --json
```

for automation.

The JSON output shall provide a stable contract suitable for:

- CI workflows
- AI agents
- MCP integrations
- Explorer

### Prioritize Actionable Feedback

Review output should emphasize user decisions rather than raw data.

Examples:

Preferred:

```text
Roadmap v0.8.0 is missing Outcomes.
Add an Outcomes section before implementation begins.
```

Avoid:

```json
{
  "section_missing": true
}
```

for human-facing output.

## Functional Requirements

### Artifact Summary

Review Mode shall report:

- total artifacts discovered
- artifact counts by type
- unknown artifacts
- invalid artifacts

Example:

```text
Artifacts:
- Requirements: 12
- ADRs: 8
- Roadmaps: 5
- Unknown: 2
```

### Validation Summary

Review Mode shall identify:

- missing required sections
- schema violations
- invalid artifact structures

### Relationship Summary

Review Mode shall identify:

- broken references
- missing linked artifacts
- duplicate identifiers
- invalid self-references

### Prioritized Issues

Review Mode shall provide an ordered list of issues requiring attention.

Prioritization should consider:

1. Invalid artifacts
2. Broken relationships
3. Missing required structure
4. Missing recommended improvements

### Suggested Actions

Where possible, Review Mode shall recommend next steps.

Examples:

```text
Run:
rac schema requirement --template
```

or:

```text
Add missing Metrics section.
```

## Non-Goals

Review Mode shall not:

- edit artifacts automatically
- rewrite requirements
- generate AI content
- replace existing commands
- introduce a separate storage model
- depend on Explorer

## Interfaces

### CLI

Required:

```bash
rac review <path>
```

Optional:

```bash
rac review <path> --json
```

### Service Layer

Review functionality shall exist as reusable repository intelligence.

Explorer, MCP, and future integrations shall consume the same review capability.

## Success Criteria

Review Mode is successful when:

- Users can understand repository health from one command.
- Existing RAC capabilities are easier to discover.
- Explorer can display review results without implementing review logic.
- Agents can consume review results without understanding RAC internals.
- CI workflows can enforce product knowledge quality.

## Related Artifacts

- ADR: Repository Intelligence as the Value Layer
- ADR: Explorer as a Consumer
- Roadmap: v0.8.0 Review Mode

## Future Considerations

Future iterations may add:

- Review history
- Repository scoring
- Trend analysis
- Configurable review policies
- Organization-specific rules

These capabilities should extend the review model without changing the core workflow.
```