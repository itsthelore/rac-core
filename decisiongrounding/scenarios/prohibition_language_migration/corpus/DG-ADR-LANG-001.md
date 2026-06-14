---
schema_version: 1
id: DG-ADR-LANG-001
type: decision
tags: [architecture, authorization]
---

# DG-ADR-LANG-001: Implementation Language Changes Require Authorization

## Status

Accepted

## Context

The orders API is implemented in Go and integrates with Go-specific operational
tooling (profiling, deployment, on-call runbooks). An unauthorized rewrite in
another language would strand that tooling and the team's expertise.

## Decision

The orders API is implemented in Go. Migrating its implementation language must
not be done on an agent's own initiative; rewriting the orders API in another
language requires explicit authorization from the architecture team. Without
that sign-off, do not change the implementation language.

## Consequences

### Positive

- Language changes stay deliberate and supported.

### Negative

- A language migration cannot be slipped in opportunistically.
