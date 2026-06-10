---
schema_version: 1
id: RAC-KTQ63DSSTZPB
type: design
---
# Explorer Import Workflow

## Context

RAC supports converting existing documents into structured product knowledge through ingestion.

The CLI workflow is optimized for automation:

```text
rac ingest document.pdf
```

Explorer requires a guided workflow that helps users understand what knowledge has been discovered before committing changes.

Importing is often a user's first interaction with RAC, so trust and transparency are critical.

---

## User Need

Users need to:

- Bring existing product documents into RAC
- Understand what was detected
- Review generated artifacts
- Control repository changes

without learning ingestion commands.

---

## Design

Explorer shall provide a guided import flow.

Example:

```text
Import Knowledge

Selected:

Product Requirements.pdf


Detected:

Requirements    12
Decisions        3
Roadmaps         1


Review Import
```

---

## Import Review

Before repository changes occur, users should understand:

- What artifacts will be created
- Where files will be placed
- What content was extracted

Example:

```text
New Artifacts

REQ-001 Payment Retry Logic

ADR-002 Provider Selection
```

---

## Confirmation

Import shall require explicit confirmation.

Explorer shall never silently mutate repositories.

---

## Constraints

- RAC Core owns ingestion
- Explorer owns workflow presentation only
- Import must remain deterministic
- No AI interpretation

---

## Accessibility

Import status shall use text labels as well as visual indicators.

---

## Related Roadmaps

- v0.8.4-explorer-action-workflow

---

## Related Decisions

- ADR-015
