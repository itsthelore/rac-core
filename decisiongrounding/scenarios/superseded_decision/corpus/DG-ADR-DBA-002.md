---
schema_version: 1
id: DG-ADR-DBA-002
type: decision
tags: [data-access, architecture]
---

# DG-ADR-DBA-002: Route Data Access Through the Repository Layer

## Status

Accepted

## Context

Direct database reads from handlers spread query logic across the codebase and
made a planned schema change unsafe. We are consolidating data access.

## Decision

Handlers must not access the database directly. Reads of the orders table from a
handler are prohibited; handlers must call the repository layer instead.

## Consequences

### Positive

- Query logic is centralised and the schema can evolve safely.

### Negative

- One more layer for simple reads.

## Related Decisions

- This decision supersedes DG-ADR-DBA-001.
