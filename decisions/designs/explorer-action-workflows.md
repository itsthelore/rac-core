# Design: Explorer Action Workflows

## Status

Proposed

## Purpose

Define how users move from repository findings to repository maintenance activities.

Explorer should not merely identify issues.

Explorer should help users act on findings efficiently.

## Design Principles

### Findings Must Be Actionable

Every finding should provide a clear next step.

Users should not need to manually locate affected files.

### Navigation Before Editing

Explorer is responsible for:

- locating artifacts
- explaining findings
- recommending actions

Explorer is not responsible for editing content.

### Minimise Friction

The path between:

```text
Issue Found
```

and

```text
Issue Addressed
```

should be as short as possible.

## Supported Actions

### Open Artifact

Navigate directly to the affected artifact.

### Open Related Artifact

Navigate to linked artifacts.

### Show Recommendation

Display recommendation details.

### Show Relationship Impact

Display connected artifacts affected by the finding.

### Open In Editor

Launch configured editor for remediation.

### Export Finding

Allow findings to be shared externally.

## Example Workflow

```text
Finding
    ↓
Recommendation
    ↓
Open Artifact
    ↓
Open In Editor
    ↓
User Remediates
```

## Non-Goals

Explorer shall not:

- edit artifacts directly
- save content changes
- replace editing tools

## Related Artifacts

- Requirement: Product Knowledge Navigator (Explorer)
- DESIGN-editor-integration
- DESIGN-recommendations