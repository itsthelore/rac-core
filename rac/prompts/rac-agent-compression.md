---
schema_version: 1
id: RAC-KV2J380T38DX
type: prompt
---
# RAC Context Compression Handoff

## Objective

Produce a compact handoff that lets a fresh coding session resume RAC work
without the original conversation.

## Input

The current working session: the active goal, the approved scope, the
changes made so far, the constraints in play, and any open questions.

## Instructions

Create a compact handoff for a fresh coding session.

Include only:

- goal
- approved scope
- files changed or likely touched
- architecture constraints
- tests required
- commands to run
- unresolved questions

## Output

A short handoff covering exactly the items above, ready to seed a new
session.

## Constraints

- Do not include conversation history.

## Related Decisions

- ADR-047
