---
schema_version: 1
id: DG-ADR-DBA-001
type: decision
tags: [data-access]
---

# DG-ADR-DBA-001: Handlers May Read the Database Directly

## Status

Superseded

## Context

In the early service, handlers queried the database directly to keep the call
path short while the schema was small and stable.

## Decision

Request handlers may read the database directly using inline SQL when it keeps
the code simple. Direct reads from the orders table from a handler are
permitted.

## Consequences

### Positive

- Fewer layers for simple reads.

## Related Decisions

- Superseded by DG-ADR-DBA-002.
